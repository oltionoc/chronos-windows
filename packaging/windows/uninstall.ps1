<#
Chronos — removal, run by the uninstaller as Administrator.

Removes the services, the firewall rule and the backup task. The data
directory (database, backups, config with its secrets) is KEPT unless
-RemoveData is passed: uninstalling to reinstall or upgrade must never cost
a client their payroll history.
#>
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [Parameter(Mandatory = $true)][string]$DataDir,
    [switch]$RemoveData
)

$ErrorActionPreference = 'Continue'

foreach ($id in @('ChronosWorker', 'ChronosServer')) {
    if (Get-Service -Name $id -ErrorAction SilentlyContinue) {
        Stop-Service $id -Force -ErrorAction SilentlyContinue
        $wrapper = Join-Path $AppDir "services\$id.exe"
        if (Test-Path -LiteralPath $wrapper) { & $wrapper uninstall | Out-Host }
        else { & sc.exe delete $id | Out-Host }
    }
}

if (Get-Service -Name ChronosPostgres -ErrorAction SilentlyContinue) {
    Stop-Service ChronosPostgres -Force -ErrorAction SilentlyContinue
    & (Join-Path $AppDir 'pgsql\bin\pg_ctl.exe') unregister -N ChronosPostgres | Out-Host
}

Remove-NetFirewallRule -DisplayName 'Chronos' -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'Chronos Backup' -Confirm:$false -ErrorAction SilentlyContinue

if ($RemoveData) {
    Remove-Item -LiteralPath $DataDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Removed $DataDir"
}
else {
    Write-Host "Chronos was removed. The database, backups and configuration were kept in:"
    Write-Host "  $DataDir"
}
exit 0
