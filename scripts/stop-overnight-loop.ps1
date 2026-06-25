<#
.SYNOPSIS
  Stop the overnight-improve background loop job.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$PidFile = Join-Path $RepoRoot ".autopilot\overnight-loop.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "No overnight loop pid file found."
    exit 0
}

$jobId = Get-Content $PidFile
Remove-Item $PidFile -Force
$job = Get-Job -Id $jobId -ErrorAction SilentlyContinue
if ($job) {
    Stop-Job -Id $jobId -ErrorAction SilentlyContinue
    Remove-Job -Id $jobId -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped overnight loop job $jobId."
} else {
    Write-Host "Job $jobId not found (already stopped)."
}
