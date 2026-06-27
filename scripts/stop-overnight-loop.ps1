<#
.SYNOPSIS
  Stop the Cursor-monitored overnight @it loop.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$PidFile = Join-Path $RepoRoot ".autopilot\overnight-loop.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "No overnight loop pid file found."
    exit 0
}

$stored = (Get-Content $PidFile -Raw).Trim()
Remove-Item $PidFile -Force

$job = Get-Job -Id $stored -ErrorAction SilentlyContinue
if ($job) {
    Stop-Job -Id $stored -ErrorAction SilentlyContinue
    Remove-Job -Id $stored -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped overnight loop job $stored."
    exit 0
}

$proc = Get-Process -Id $stored -ErrorAction SilentlyContinue
if ($proc) {
    Stop-Process -Id $stored -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped overnight loop process $stored."
    exit 0
}

Write-Host "Overnight loop $stored not found (already stopped)."
