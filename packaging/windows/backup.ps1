<#
Chronos nightly backup — the Windows counterpart of ops/backup.sh.

Run by the "Chronos Backup" scheduled task (daily 02:30 and at every boot,
with -IfMissed so a boot shortly after a good backup does nothing).

Writes DataDir\backups\chronos-<UTC stamp>.dump (pg_dump custom format),
verifies it with pg_restore --list before trusting it, prunes old dumps, and
writes LAST_BACKUP — the marker the app reads to raise backup_missing /
backup_failed / backup_stale. The marker is written last and atomically, so
a half-written backup can never look like a good one.
#>
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [Parameter(Mandatory = $true)][string]$DataDir,
    # Skip if a verified dump from the last 24 hours already exists.
    [switch]$IfMissed
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Backups = Join-Path $DataDir 'backups'
$Marker = Join-Path $Backups 'LAST_BACKUP'
$PgBin = Join-Path $AppDir 'pgsql\bin'
New-Item -ItemType Directory -Force -Path $Backups | Out-Null

function Read-EnvFile([string]$Path) {
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { $values[$Matches[1]] = $Matches[2] }
    }
    return $values
}

function Write-Marker([string]$Status, [string]$File) {
    # Plain ASCII, no byte-order mark: the app parses the first field as an
    # ISO timestamp, and a BOM would make every marker unreadable.
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $tmp = "$Marker.tmp"
    Set-Content -LiteralPath $tmp -Value "$stamp $Status $File" -Encoding ascii
    Move-Item -LiteralPath $tmp -Destination $Marker -Force
}

$config = Read-EnvFile (Join-Path $DataDir 'chronos.env')
$retentionDays = if ($config.ContainsKey('BACKUP_RETENTION_DAYS')) { [int]$config['BACKUP_RETENTION_DAYS'] } else { 14 }

if ($IfMissed) {
    $recent = Get-ChildItem -LiteralPath $Backups -Filter 'chronos-*.dump' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt (Get-Date).AddHours(-24) }
    if ($recent) { exit 0 }
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$name = "chronos-$stamp.dump"
$target = Join-Path $Backups $name
$part = "$target.part"

$env:PGPASSWORD = $config['POSTGRES_PASSWORD']
try {
    & (Join-Path $PgBin 'pg_dump.exe') --format=custom --compress=6 --file=$part `
        -h $config['POSTGRES_HOST'] -p $config['POSTGRES_PORT'] -U $config['POSTGRES_USER'] $config['POSTGRES_DB']
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }

    # A dump that cannot be listed cannot be restored either; find that out
    # now rather than on the day it is needed. Kept as .INVALID for inspection.
    & (Join-Path $PgBin 'pg_restore.exe') --list $part | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Move-Item -LiteralPath $part -Destination "$target.INVALID" -Force
        throw 'dump failed verification'
    }
    Move-Item -LiteralPath $part -Destination $target -Force
    Write-Marker 'ok' $name

    # Prune by age. Invalid dumps are deliberately never pruned: they are
    # evidence of a problem someone should look at.
    Get-ChildItem -LiteralPath $Backups -Filter 'chronos-*.dump' -File |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$retentionDays) } |
        Remove-Item -Force
    exit 0
}
catch {
    Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
    Write-Marker 'failed' '-'
    # Report and exit non-zero — not Write-Error, which under
    # ErrorActionPreference=Stop would throw out of this catch, skip the exit
    # code and take the caller (the installer) down with it. A failed backup
    # is what the app's backup_failed alert is for.
    Write-Warning "Chronos backup failed: $($_.Exception.Message)"
    exit 1
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
