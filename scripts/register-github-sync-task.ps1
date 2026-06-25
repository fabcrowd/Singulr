<#
.SYNOPSIS
  Register an hourly Windows scheduled task to sync local changes to GitHub.

.PARAMETER IntervalHours
  Hours between sync runs (default 1).

.EXAMPLE
  .\scripts\register-github-sync-task.ps1
#>
param(
    [int]$IntervalHours = 1
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$SyncScript = Join-Path $RepoRoot "scripts\sync-to-github.ps1"
$TaskName = "Singulr GitHub Sync"

if ($IntervalHours -lt 1) {
    Write-Error "IntervalHours must be >= 1"
}

if (-not (Test-Path $SyncScript)) {
    Write-Error "Missing sync script: $SyncScript"
}

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$SyncScript`""
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $arguments `
    -WorkingDirectory $RepoRoot

$startAt = (Get-Date).AddMinutes(2)
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $startAt `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName"
Write-Host "  Script:  $SyncScript"
Write-Host "  Every:   ${IntervalHours}h (first run ~2 minutes from now)"
Write-Host "  Log:     $RepoRoot\.autopilot\github-sync.log"
Write-Host "  Remove:  .\scripts\unregister-github-sync-task.ps1"
