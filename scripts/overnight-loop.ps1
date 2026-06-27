<#
.SYNOPSIS
  Cursor-monitored @it overnight loop — wakes Agent on an interval.

.DESCRIPTION
  Emits AGENT_LOOP_TICK_overnight with a JSON payload each interval.
  Pair with docs/autopilot/IT_LOOP_PROMPT.md in an Agent chat.

  Runs in the foreground so Cursor Shell notify_on_output can wake the agent.
  Do NOT use Start-Job / hidden Start-Process for this loop.

.PARAMETER IntervalMinutes
  Minutes between ticks (default 30, minimum 5).

.PARAMETER RunOnce
  Emit one tick immediately and exit (no loop).

.EXAMPLE
  .\scripts\overnight-loop.ps1 -IntervalMinutes 30
#>
param(
    [int]$IntervalMinutes = 30,
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$PidFile = Join-Path $RepoRoot ".autopilot\overnight-loop.pid"
$LogFile = Join-Path $RepoRoot ".autopilot\overnight-it-ticks.log"
$PromptFile = Join-Path $RepoRoot "tasks\overnight-it-tick-prompt.txt"

if ($IntervalMinutes -lt 5) {
    Write-Error "IntervalMinutes must be >= 5"
}

if (-not (Test-Path $PromptFile)) {
    Write-Error "Tick prompt not found: $PromptFile"
}

function Get-TickPayload {
    $prompt = (Get-Content -Path $PromptFile -Raw).Trim()
    return (@{ prompt = $prompt } | ConvertTo-Json -Compress)
}

function Write-OvernightTick {
    $payload = Get-TickPayload
    $line = "$(Get-Date -Format o) AGENT_LOOP_TICK_overnight $payload"
    Add-Content -Path $LogFile -Value $line
    Write-Output "AGENT_LOOP_TICK_overnight $payload"
}

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
Set-Content -Path $PidFile -Value $PID

Write-Host "Overnight @it loop started (PID $PID)"
Write-Host "  Interval:  ${IntervalMinutes}m"
Write-Host "  Prompt:    $PromptFile"
Write-Host "  Guide:     docs\autopilot\IT_LOOP_PROMPT.md"
Write-Host "  Log:       $LogFile"
Write-Host "  Stop:      .\scripts\stop-overnight-loop.ps1"
Write-Host ""
Write-Host "Paste LOOP PROMPT from docs\autopilot\IT_LOOP_PROMPT.md into Agent now."

if ($RunOnce) {
    Write-OvernightTick
    exit 0
}

while ($true) {
    Start-Sleep -Seconds ($IntervalMinutes * 60)
    Write-OvernightTick
}
