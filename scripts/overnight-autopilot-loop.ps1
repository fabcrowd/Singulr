<#
.SYNOPSIS
  Background ticker for repo-lead / autopilot overnight sessions.

.PARAMETER TaskSlug
  Feature folder name under docs/autopilot/ (e.g. network-trust-registry).

.PARAMETER IntervalMinutes
  Minutes between ticks (default 45, minimum 5).

.EXAMPLE
  .\scripts\overnight-autopilot-loop.ps1 -TaskSlug network-trust-registry -IntervalMinutes 45
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskSlug,
    [int]$IntervalMinutes = 45
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$PidFile = Join-Path $RepoRoot ".autopilot\overnight-loop.pid"
$LogFile = Join-Path $RepoRoot "docs\autopilot\$TaskSlug\loop-ticks.log"
$TickName = "AGENT_LOOP_TICK_$TaskSlug"

if ($IntervalMinutes -lt 5) {
    Write-Error "IntervalMinutes must be >= 5"
}

$tickPrompt = @(
    "Repo-lead TICK ($TaskSlug): Read docs/autopilot/REPO_LEAD_LOOP_PROMPT.md TICK handler."
    "Follow senior-singulr-dev skill. python -m orchestrator autopilot status; one requirement iteration or verify grind."
) -join " "

$payload = @{ prompt = $tickPrompt; task = $TaskSlug } | ConvertTo-Json -Compress -EscapeHandling EscapeNonAscii

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
    param($Root, $Minutes, $Payload, $Log, $Tick)
    Set-Location $Root
    while ($true) {
        Start-Sleep -Seconds ($Minutes * 60)
        $line = "$(Get-Date -Format o) $Tick $Payload"
        Add-Content -Path $Log -Value $line
        Write-Output $line
    }
} -ArgumentList $RepoRoot, $IntervalMinutes, $payload, $LogFile, $TickName

$job.Id | Set-Content $PidFile
Write-Host "Repo-lead loop started (job $($job.Id), every ${IntervalMinutes}m, task=$TaskSlug)."
Write-Host "Log: $LogFile"
Write-Host "Stop: .\scripts\stop-overnight-loop.ps1"
Write-Host "Paste LOOP PROMPT from docs/autopilot/REPO_LEAD_LOOP_PROMPT.md into Agent now."
