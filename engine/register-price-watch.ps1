# Registers the Shopbot watcher without starting a shopping run.
# KEEP THIS FILE PURE ASCII FOR WINDOWS POWERSHELL 5.1.
param(
  [string]$TaskName = 'ClaudePriceWatch'
)

$ErrorActionPreference = 'Stop'

$watcherPath = Join-Path $PSScriptRoot 'price-watch.ps1'
if (-not (Test-Path -LiteralPath $watcherPath -PathType Leaf)) {
  throw "Watcher script not found: $watcherPath"
}
$watcherPath = (Resolve-Path -LiteralPath $watcherPath).Path

$powerShellPath = Join-Path $PSHOME 'powershell.exe'
$arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $watcherPath
$action = New-ScheduledTaskAction -Execute $powerShellPath -Argument $arguments -WorkingDirectory (Split-Path -Parent $watcherPath)
$triggers = @(
  New-ScheduledTaskTrigger -Daily -At '9:23 AM'
  New-ScheduledTaskTrigger -Daily -At '4:23 PM'
)
$settings = New-ScheduledTaskSettingsSet
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description 'Shopbot price watcher; verifies configured retailer pages before alerting.'

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Write-Output "Registered $TaskName for daily runs at 9:23 AM and 4:23 PM."
