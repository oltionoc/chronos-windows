<#
Restore a Chronos backup. DESTRUCTIVE: replaces the current database contents
with the dump's. Run from an Administrator PowerShell:

    & "C:\Program Files\Chronos\scripts\restore.ps1" `
        -DumpFile "C:\ProgramData\Chronos\backups\chronos-20260917-023000.dump"

It verifies the dump before touching anything, stops Chronos so nothing
reads a half-restored database, restores, and starts Chronos again.
#>
param(
    [Parameter(Mandatory = $true)][string]$DumpFile,
    [string]$AppDir = (Join-Path $env:ProgramFiles 'Chronos'),
    [string]$DataDir = (Join-Path $env:ProgramData 'Chronos')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath $DumpFile)) { throw "No such file: $DumpFile" }

$PgBin = Join-Path $AppDir 'pgsql\bin'
$config = @{}
foreach ($line in Get-Content -LiteralPath (Join-Path $DataDir 'chronos.env')) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { $config[$Matches[1]] = $Matches[2] }
}

Write-Host "About to REPLACE the Chronos database with:"
Write-Host "  $DumpFile"
Write-Host ''
Write-Host 'Everything currently in it (punches, daily status, payroll runs) is lost.'
$answer = Read-Host 'Type RESTORE to continue'
if ($answer -ne 'RESTORE') { Write-Host 'Aborted.'; exit 1 }

Write-Host 'Verifying dump...'
& (Join-Path $PgBin 'pg_restore.exe') --list $DumpFile | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The dump failed verification. Nothing was changed.' }

Write-Host 'Stopping Chronos...'
Stop-Service ChronosWorker -ErrorAction SilentlyContinue
Stop-Service ChronosServer -ErrorAction SilentlyContinue

$env:PGPASSWORD = $config['POSTGRES_PASSWORD']
try {
    Write-Host 'Restoring...'
    & (Join-Path $PgBin 'pg_restore.exe') --clean --if-exists --no-owner `
        -h $config['POSTGRES_HOST'] -p $config['POSTGRES_PORT'] -U $config['POSTGRES_USER'] -d $config['POSTGRES_DB'] $DumpFile
    if ($LASTEXITCODE -ne 0) { Write-Warning 'pg_restore reported problems; check the output above.' }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Write-Host 'Starting Chronos...'
    Start-Service ChronosServer
    Start-Service ChronosWorker
}
Write-Host 'Done. Open the app and confirm the most recent punches are there.'
