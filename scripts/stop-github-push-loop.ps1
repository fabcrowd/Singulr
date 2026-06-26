<#
.SYNOPSIS
  Stop the github-push-loop background process.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$PidFile = Join-Path $RepoRoot ".autopilot\github-push-loop.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "No github push loop pid file found."
    exit 0
}

$loopPid = [int](Get-Content $PidFile -Raw).Trim()
Remove-Item $PidFile -Force

$proc = Get-Process -Id $loopPid -ErrorAction SilentlyContinue
if ($proc) {
    Stop-Process -Id $loopPid -Force
    Write-Host "Stopped github push loop (PID $loopPid)."
} else {
    Write-Host "Process $loopPid not found (already stopped)."
}
