<#
.SYNOPSIS
  Remove the hourly GitHub sync scheduled task.
#>
$ErrorActionPreference = "Stop"
$TaskName = "Singulr GitHub Sync"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Task not found: $TaskName"
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Removed scheduled task: $TaskName"
