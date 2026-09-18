<#
Build ChronosSetup-<version>.exe on Windows.

    powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1 -Version 0.1.0

Needs: Python 3.12, Node 20, a C compiler for Nuitka (Visual Studio Build
Tools; Nuitka can also fetch MinGW itself), and Inno Setup 6. The GitHub
Actions workflow (.github/workflows/windows-installer.yml) runs exactly this
on a clean Windows machine, so a local Windows setup is optional.

Nuitka flags come from packaging/nuitka/*.args — the same files the Linux
compile check uses — so the two can never build different programs.
#>
param(
    [string]$Version = '0.1.0-beta',
    # PostgreSQL major version must match the Docker deployment (16), so a
    # dump taken on either restores on the other.
    [string]$PostgresVersion = '16.4-1',
    [string]$WinSWVersion = '2.12.0'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$Here = $PSScriptRoot
$Stage = Join-Path $Here 'stage'
$Build = Join-Path $Here 'build'
$Downloads = Join-Path $Here 'downloads'

function Step([string]$Message) { Write-Host "`n==> $Message" }

function Invoke-Checked([string]$What, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit $LASTEXITCODE)" }
}

function Get-NuitkaArgs([string]$Name) {
    Get-Content (Join-Path $Root "packaging\nuitka\$Name.args") |
        Where-Object { $_ -and ($_ -notmatch '^\s*#') } |
        ForEach-Object { $_.Trim() }
}

# Windows file-version resources must be four integers: 0.1.0-beta -> 0.1.0.0
$numeric = ($Version -replace '[^0-9.].*$', '')
$parts = @($numeric.Split('.') | Where-Object { $_ -ne '' })
while ($parts.Count -lt 4) { $parts += '0' }
$FileVersion = ($parts[0..3] -join '.')
$WindowsMeta = @(
    '--windows-company-name=Solis Labs',
    '--windows-product-name=Chronos',
    "--windows-file-version=$FileVersion",
    "--windows-product-version=$FileVersion",
    '--assume-yes-for-downloads'
)

Remove-Item -Recurse -Force $Stage, $Build -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Stage, $Build, $Downloads | Out-Null

Step 'Python dependencies'
Invoke-Checked 'pip install' { python -m pip install -q --upgrade pip }
Invoke-Checked 'pip install' { python -m pip install -q -r (Join-Path $Root 'backend\requirements.txt') }
Invoke-Checked 'pip install' { python -m pip install -q -r (Join-Path $Root 'worker\requirements.txt') }
# Pinned to the version verified by the Linux compile check and the first
# Windows build, so the compiler cache stays valid between runs.
Invoke-Checked 'pip install' { python -m pip install -q 'nuitka==4.2.1' ordered-set zstandard }
python -m pip show nuitka | Select-String '^Version'

Step 'Web UI'
Push-Location (Join-Path $Root 'frontend')
try {
    Invoke-Checked 'npm ci' { npm ci --no-audit --no-fund }
    Invoke-Checked 'npm run build' { npm run build }
}
finally { Pop-Location }

Step 'Compiling chronos-server'
Push-Location (Join-Path $Root 'backend')
try {
    $serverArgs = @(Get-NuitkaArgs 'server') + $WindowsMeta + @("--output-dir=$Build\server", 'chronos_server.py')
    Invoke-Checked 'Nuitka (server)' { python -m nuitka @serverArgs }
}
finally { Pop-Location }

Step 'Compiling chronos-worker'
Push-Location (Join-Path $Root 'worker')
try {
    $workerArgs = @(Get-NuitkaArgs 'worker') + $WindowsMeta + @("--output-dir=$Build\worker", 'chronos_worker.py')
    Invoke-Checked 'Nuitka (worker)' { python -m nuitka @workerArgs }
}
finally { Pop-Location }

Step 'Staging'
Copy-Item -Recurse (Join-Path $Build 'server\chronos_server.dist') (Join-Path $Stage 'server')
Copy-Item -Recurse (Join-Path $Root 'frontend\dist') (Join-Path $Stage 'server\web')
Copy-Item -Recurse (Join-Path $Build 'worker\chronos_worker.dist') (Join-Path $Stage 'worker')

# Nothing but the migrations may ship as readable Python.
$leaked = Get-ChildItem -Recurse -Path (Join-Path $Stage 'server'), (Join-Path $Stage 'worker') -Include '*.py' |
    Where-Object { $_.FullName -notmatch '\\alembic\\' }
if ($leaked) { throw "Python source found in the build: $($leaked.FullName -join ', ')" }

Step "PostgreSQL $PostgresVersion binaries"
$pgZip = Join-Path $Downloads "postgresql-$PostgresVersion-windows-x64-binaries.zip"
if (-not (Test-Path $pgZip)) {
    $url = "https://get.enterprisedb.com/postgresql/postgresql-$PostgresVersion-windows-x64-binaries.zip"
    try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $pgZip }
    catch { throw "Could not download $url. Check the PostgreSQL version exists as a binaries archive and pass -PostgresVersion." }
}
Write-Host "sha256 $((Get-FileHash $pgZip -Algorithm SHA256).Hash)  $(Split-Path -Leaf $pgZip)"
$pgExtract = Join-Path $Build 'pgsql-extract'
Expand-Archive -Path $pgZip -DestinationPath $pgExtract -Force
$pgStage = Join-Path $Stage 'pgsql'
New-Item -ItemType Directory -Force -Path $pgStage | Out-Null
# Only what a server needs: pgAdmin, StackBuilder, headers and docs stay out.
foreach ($dir in 'bin', 'lib', 'share') {
    Copy-Item -Recurse (Join-Path $pgExtract "pgsql\$dir") (Join-Path $pgStage $dir)
}

Step "WinSW $WinSWVersion"
$winswDir = Join-Path $Stage 'winsw'
New-Item -ItemType Directory -Force -Path $winswDir | Out-Null
$winsw = Join-Path $winswDir 'WinSW-x64.exe'
Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/winsw/winsw/releases/download/v$WinSWVersion/WinSW-x64.exe" -OutFile $winsw
Write-Host "sha256 $((Get-FileHash $winsw -Algorithm SHA256).Hash)  WinSW-x64.exe"

Step 'Installer'
$iscc = @(
    (Get-Command iscc.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup 6 (ISCC.exe) not found' }
Push-Location $Here
try { Invoke-Checked 'Inno Setup' { & $iscc "/DAppVersion=$Version" 'chronos.iss' } }
finally { Pop-Location }

$installer = Join-Path $Here "Output\ChronosSetup-$Version.exe"
Write-Host "`nBuilt: $installer ($([math]::Round((Get-Item $installer).Length / 1MB, 1)) MB)"
