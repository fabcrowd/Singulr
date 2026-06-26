<#
.SYNOPSIS
  Cursor-monitored loop: commit local changes and push to GitHub on an interval.

.DESCRIPTION
  Runs scripts/sync-to-github.ps1 each tick. Emits AGENT_LOOP_TICK_github_push so
  Cursor can notify the agent (optional). Writes PID to .autopilot/github-push-loop.pid.

  This is git sync only — it does NOT replace the coding overnight loop.

.PARAMETER IntervalMinutes
  Minutes between push attempts (default 30).

.PARAMETER TargetBranch
  Remote branch(es) to push to. Default: master and main (keeps both in sync).

.PARAMETER RunOnce
  Sync once and exit (no loop).

.EXAMPLE
  .\scripts\github-push-loop.ps1 -IntervalMinutes 15 -TargetBranch master,main
#>
param(
    [int]$IntervalMinutes = 30,
    [string[]]$TargetBranch = @("master", "main"),
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$SyncScript = Join-Path $RepoRoot "scripts\sync-to-github.ps1"
$PidFile = Join-Path $RepoRoot ".autopilot\github-push-loop.pid"

if ($IntervalMinutes -lt 1) {
    Write-Error "IntervalMinutes must be >= 1"
}

function Invoke-GitHubSync {
    $branchArgs = @()
    foreach ($b in $TargetBranch) {
        $branchArgs += "-TargetBranch"
        $branchArgs += $b
    }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $SyncScript @branchArgs 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
    }
    $text = ($output | Out-String).Trim()
    $pushed = $text -match "OK: synced"
    $skipped = $text -match "SKIP:"
    $status = if ($exitCode -ne 0) { "error" } elseif ($pushed) { "pushed" } elseif ($skipped) { "skipped" } else { "ok" }
    return @{ Status = $status; ExitCode = $exitCode; Output = $text }
}

function Write-Tick {
    param([hashtable]$Result)
    $escaped = $Result.Output -replace '\\', '\\\\' -replace '"', '\"' -replace "`r?`n", ' '
    $payload = "{`"status`":`"$($Result.Status)`",`"targets`":`"$($TargetBranch -join ',')`",`"detail`":`"$escaped`"}"
    Write-Output "AGENT_LOOP_TICK_github_push $payload"
}

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null
Set-Content -Path $PidFile -Value $PID

Write-Host "GitHub push loop started (PID $PID)"
Write-Host "  Interval:  ${IntervalMinutes}m"
Write-Host "  Target:    $(($TargetBranch | ForEach-Object { "origin/$_" }) -join ', ')"
Write-Host "  Log:       $RepoRoot\.autopilot\github-sync.log"
Write-Host "  Stop:      .\scripts\stop-github-push-loop.ps1"

$first = Invoke-GitHubSync
Write-Tick $first

if ($RunOnce) {
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    exit $first.ExitCode
}

$seconds = $IntervalMinutes * 60
while ($true) {
    Start-Sleep -Seconds $seconds
    $result = Invoke-GitHubSync
    Write-Tick $result
}
