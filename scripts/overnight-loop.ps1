<#
.SYNOPSIS
  Background ticker that wakes Cursor Agent on an interval for overnight-improve loop.

.DESCRIPTION
  Emits AGENT_LOOP_TICK_overnight_improve with a JSON payload each interval.
  Pair with docs/autopilot/overnight-improve/LOOP_PROMPT.md in an Agent chat.

.PARAMETER IntervalMinutes
  Minutes between ticks (default 45).

.EXAMPLE
  .\scripts\overnight-loop.ps1 -IntervalMinutes 45
#>
param(
    [int]$IntervalMinutes = 45
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$PidFile = Join-Path $RepoRoot ".autopilot\overnight-loop.pid"
$LogFile = Join-Path $RepoRoot "docs\autopilot\overnight-improve\loop-ticks.log"

if ($IntervalMinutes -lt 5) {
    Write-Error "IntervalMinutes must be >= 5"
}

$tickPrompt = @(
    "Overnight-improve TICK: Read docs/autopilot/overnight-improve/LOOP_PROMPT.md section TICK HANDLER."
    "Run python -m orchestrator autopilot status; execute one requirement iteration or deep-bug-hunt if all reqs pending work is blocked."
) -join " "

$payload = @{ prompt = $tickPrompt } | ConvertTo-Json -Compress -EscapeHandling EscapeNonAscii

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

if (Test-Path $PidFile) {
    $oldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        Write-Host "Overnight loop already running (PID $oldPid). Stop with scripts\stop-overnight-loop.ps1"
        exit 1
    }
}

$job = Start-Job -ScriptBlock {
    param($Root, $Minutes, $Payload, $Log)
    Set-Location $Root
    while ($true) {
        Start-Sleep -Seconds ($Minutes * 60)
        $line = "$(Get-Date -Format o) AGENT_LOOP_TICK_overnight_improve $Payload"
        Add-Content -Path $Log -Value $line
        Write-Output $line
    }
} -ArgumentList $RepoRoot, $IntervalMinutes, $payload, $LogFile

$job.Id | Set-Content $PidFile
Write-Host "Overnight loop started (job id $($job.Id), every ${IntervalMinutes}m)."
Write-Host "Log: $LogFile"
Write-Host "Stop: .\scripts\stop-overnight-loop.ps1"
Write-Host "First tick fires after ${IntervalMinutes} minutes — run LOOP PROMPT once now in Agent."
