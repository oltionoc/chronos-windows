<#
Chronos — post-copy setup, run by the installer as Administrator.

Idempotent: a first install creates everything, an upgrade (same script,
existing data) only restarts services and migrates. Nothing here ever deletes
data.

    install.ps1 -AppDir "C:\Program Files\Chronos" -DataDir "C:\ProgramData\Chronos"

Layout it produces:
    AppDir\server\chronos-server.exe   compiled API + web UI  (service ChronosServer)
    AppDir\worker\chronos-worker.exe   compiled device sync   (service ChronosWorker)
    AppDir\pgsql\                      PostgreSQL binaries    (service ChronosPostgres)
    AppDir\services\                   WinSW service wrappers
    DataDir\chronos.env                config + secrets, readable by SYSTEM/Administrators only
    DataDir\pgdata\                    the database
    DataDir\backups\                   nightly dumps + LAST_BACKUP marker
    DataDir\logs\                      service and install logs
#>
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [Parameter(Mandatory = $true)][string]$DataDir,
    [int]$Port = 8080
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$LogDir = Join-Path $DataDir 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir 'install.log') -Append | Out-Null

# Loopback-only port for PostgreSQL. Deliberately not 5432, so the install
# can never collide with (or be mistaken for) another PostgreSQL on the PC.
$PgPort = 55432
$EnvFile = Join-Path $DataDir 'chronos.env'
$PgData = Join-Path $DataDir 'pgdata'
$Backups = Join-Path $DataDir 'backups'
$PgBin = Join-Path $AppDir 'pgsql\bin'

function Write-Step([string]$Message) { Write-Host "==> $Message" }

function New-Secret([int]$Bytes = 32) {
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return -join ($buffer | ForEach-Object { $_.ToString('x2') })
}

function Protect-File([string]$Path) {
    # SYSTEM and Administrators only: this file holds the database password
    # and the session-signing secret. Inheritance off so a permissive parent
    # folder ACL cannot widen it later.
    & icacls $Path /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "could not restrict permissions on $Path" }
}

function Read-EnvFile([string]$Path) {
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { $values[$Matches[1]] = $Matches[2] }
    }
    return $values
}

function Wait-Until([scriptblock]$Condition, [int]$Seconds, [string]$What) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return }
        Start-Sleep -Seconds 1
    }
    throw "timed out after ${Seconds}s waiting for $What"
}

try {
    foreach ($dir in @($DataDir, $Backups, $LogDir, (Join-Path $DataDir 'branding'))) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

    # ---- 1. Configuration --------------------------------------------------
    if (-not (Test-Path -LiteralPath $EnvFile)) {
        Write-Step 'Generating configuration and secrets'
        $marker = Join-Path $Backups 'LAST_BACKUP'
        @(
            '# Chronos configuration. Generated at install; keep a copy somewhere safe',
            '# and OFF this machine: the secrets below cannot be recovered from a backup.',
            '',
            "POSTGRES_HOST=127.0.0.1",
            "POSTGRES_PORT=$PgPort",
            'POSTGRES_DB=chronos',
            'POSTGRES_USER=chronos',
            "POSTGRES_PASSWORD=$(New-Secret 24)",
            "POSTGRES_SUPERUSER_PASSWORD=$(New-Secret 24)",
            "JWT_SECRET=$(New-Secret 32)",
            "INTERNAL_API_KEY=$(New-Secret 32)",
            '',
            "SERVER_PORT=$Port",
            'WORKER_INTERNAL_URL=http://127.0.0.1:8100',
            "API_BASE_URL=http://127.0.0.1:$Port/api/v1",
            "BACKUP_MARKER_PATH=$marker",
            'BACKUP_RETENTION_DAYS=14',
            '',
            'DEVICE_TIMEZONE=Europe/Tirane',
            "BRANDING_LOGO_PATH=$(Join-Path $DataDir 'branding\logo.png')",
            'SYNC_INTERVAL_SECONDS=300',
            'NIGHTLY_HOUR=2',
            'NIGHTLY_MINUTE=0',
            '# Only set true if the app is served over HTTPS; over plain http the',
            '# login cookie would be dropped and nobody could sign in.',
            'COOKIE_SECURE=false'
        ) | Set-Content -LiteralPath $EnvFile -Encoding ascii
        Protect-File $EnvFile
    }
    else {
        Write-Step 'Existing configuration kept'
    }
    $config = Read-EnvFile $EnvFile
    $Port = [int]$config['SERVER_PORT']

    # ---- 2. Database cluster -----------------------------------------------
    if (-not (Test-Path -LiteralPath (Join-Path $PgData 'PG_VERSION'))) {
        Write-Step 'Initialising the database cluster'
        $pwFile = Join-Path $env:TEMP ("chronos-pg-" + [guid]::NewGuid() + '.txt')
        Set-Content -LiteralPath $pwFile -Value $config['POSTGRES_SUPERUSER_PASSWORD'] -NoNewline -Encoding ascii
        try {
            & (Join-Path $PgBin 'initdb.exe') -D $PgData -U postgres --pwfile=$pwFile -A scram-sha-256 -E UTF8 --locale=C | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
        }
        finally { Remove-Item -LiteralPath $pwFile -Force -ErrorAction SilentlyContinue }

        # Loopback only: nothing on the network ever talks to the database
        # directly, only the Chronos server on this machine.
        Add-Content -LiteralPath (Join-Path $PgData 'postgresql.conf') -Encoding ascii -Value @(
            '',
            '# --- Chronos ---',
            "listen_addresses = '127.0.0.1'",
            "port = $PgPort"
        )
    }

    # The service runs as NETWORK SERVICE (as the official installer does), so
    # that account needs the data directory. PostgreSQL refuses to run with
    # administrative rights at all.
    & icacls $PgData /grant '*S-1-5-20:(OI)(CI)F' /T /Q | Out-Null

    if (-not (Get-Service -Name ChronosPostgres -ErrorAction SilentlyContinue)) {
        Write-Step 'Registering the ChronosPostgres service'
        & (Join-Path $PgBin 'pg_ctl.exe') register -N ChronosPostgres -U 'NT AUTHORITY\NetworkService' -D $PgData -S auto -w | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'pg_ctl register failed' }
    }
    if ((Get-Service ChronosPostgres).Status -ne 'Running') { Start-Service ChronosPostgres }
    Wait-Until {
        & (Join-Path $PgBin 'pg_isready.exe') -h 127.0.0.1 -p $PgPort -q
        $LASTEXITCODE -eq 0
    } 60 'PostgreSQL to accept connections'

    # ---- 3. Application role and database ----------------------------------
    $env:PGPASSWORD = $config['POSTGRES_SUPERUSER_PASSWORD']
    $psql = Join-Path $PgBin 'psql.exe'
    $psqlArgs = @('-h', '127.0.0.1', '-p', $PgPort, '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-tAc')
    try {
        $roleExists = & $psql @psqlArgs "SELECT 1 FROM pg_roles WHERE rolname = 'chronos'"
        if ("$roleExists".Trim() -ne '1') {
            Write-Step 'Creating the chronos database role'
            # Generated hex, so it is safe inside a SQL string literal.
            & $psql @psqlArgs "CREATE ROLE chronos LOGIN PASSWORD '$($config['POSTGRES_PASSWORD'])'" | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'creating the role failed' }
        }
        $dbExists = & $psql @psqlArgs "SELECT 1 FROM pg_database WHERE datname = 'chronos'"
        if ("$dbExists".Trim() -ne '1') {
            Write-Step 'Creating the chronos database'
            & $psql @psqlArgs 'CREATE DATABASE chronos OWNER chronos' | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'creating the database failed' }
        }
    }
    finally { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }

    # ---- 4. Schema ---------------------------------------------------------
    # Migrate here, synchronously, so a failure stops the installer with a
    # message instead of leaving a service that crash-loops in the background.
    Write-Step 'Applying database migrations'
    $env:CHRONOS_ENV_FILE = $EnvFile
    & (Join-Path $AppDir 'server\chronos-server.exe') --migrate-only | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'database migration failed — see the output above' }

    # ---- 5. Services -------------------------------------------------------
    $services = Join-Path $AppDir 'services'
    $winsw = Join-Path $services 'WinSW-x64.exe'
    $definitions = @(
        @{
            Id = 'ChronosServer'; Name = 'Chronos Server'
            Description = 'Chronos attendance and payroll: API and web interface.'
            Exe = (Join-Path $AppDir 'server\chronos-server.exe'); Depends = 'ChronosPostgres'
            # Migrations already ran above; on later restarts the server runs
            # them itself, which is a no-op when the schema is current.
            Arguments = ''
        },
        @{
            Id = 'ChronosWorker'; Name = 'Chronos Worker'
            Description = 'Chronos attendance and payroll: collects punches from the attendance terminals.'
            Exe = (Join-Path $AppDir 'worker\chronos-worker.exe'); Depends = 'ChronosServer'
            Arguments = ''
        }
    )
    foreach ($svc in $definitions) {
        $wrapper = Join-Path $services ($svc.Id + '.exe')
        $xml = Join-Path $services ($svc.Id + '.xml')
        Copy-Item -LiteralPath $winsw -Destination $wrapper -Force
        @"
<service>
  <id>$($svc.Id)</id>
  <name>$($svc.Name)</name>
  <description>$($svc.Description)</description>
  <executable>$($svc.Exe)</executable>
  <arguments>$($svc.Arguments)</arguments>
  <workingdirectory>$(Split-Path -Parent $svc.Exe)</workingdirectory>
  <env name="CHRONOS_ENV_FILE" value="$EnvFile"/>
  <depend>$($svc.Depends)</depend>
  <startmode>Automatic</startmode>
  <stoptimeout>20 sec</stoptimeout>
  <onfailure action="restart" delay="10 sec"/>
  <onfailure action="restart" delay="30 sec"/>
  <onfailure action="restart" delay="60 sec"/>
  <resetfailure>1 hour</resetfailure>
  <logpath>$LogDir</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>8</keepFiles>
  </log>
</service>
"@ | Set-Content -LiteralPath $xml -Encoding utf8
        if (-not (Get-Service -Name $svc.Id -ErrorAction SilentlyContinue)) {
            Write-Step "Registering the $($svc.Id) service"
            & $wrapper install | Out-Host
            if ($LASTEXITCODE -ne 0) { throw "registering $($svc.Id) failed" }
        }
    }
    Write-Step 'Starting Chronos'
    Start-Service ChronosServer
    Start-Service ChronosWorker

    Wait-Until {
        try { (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3).StatusCode -eq 200 }
        catch { $false }
    } 90 'the Chronos server to answer'

    # ---- 6. Firewall -------------------------------------------------------
    # Private and domain networks only: staff reach the app from the office
    # LAN; a public network (hotel Wi-Fi, a phone hotspot) never should.
    if (-not (Get-NetFirewallRule -DisplayName 'Chronos' -ErrorAction SilentlyContinue)) {
        Write-Step "Opening TCP $Port on private networks"
        New-NetFirewallRule -DisplayName 'Chronos' -Direction Inbound -Protocol TCP -LocalPort $Port `
            -Action Allow -Profile Domain, Private | Out-Null
    }

    # ---- 7. Nightly backup -------------------------------------------------
    # Daily at 02:30, plus at every boot — the PC may well be off at 02:30,
    # and the backup script skips the run if one exists from the last 24h.
    $taskName = 'Chronos Backup'
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
        "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $AppDir 'scripts\backup.ps1')`" " +
        "-AppDir `"$AppDir`" -DataDir `"$DataDir`" -IfMissed")
    $triggers = @(
        (New-ScheduledTaskTrigger -Daily -At '02:30'),
        (New-ScheduledTaskTrigger -AtStartup)
    )
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Principal $principal `
        -Settings $settings -Force | Out-Null

    # First backup now, so the app never starts life showing "no backup ever ran".
    Write-Step 'Taking the first backup'
    & (Join-Path $AppDir 'scripts\backup.ps1') -AppDir $AppDir -DataDir $DataDir -IfMissed
    if ($LASTEXITCODE -ne 0) {
        # Not fatal to the install: the app raises backup_failed on its own
        # dashboard, which is where someone will actually see it.
        Write-Warning 'The first backup did not succeed; Chronos will show a backup alert until one does.'
    }

    Write-Step "Done. Chronos is running at http://localhost:$Port"
    exit 0
}
catch {
    Write-Host "INSTALL FAILED: $($_.Exception.Message)"
    Write-Host "Full log: $(Join-Path $LogDir 'install.log')"
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
