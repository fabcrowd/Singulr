<#
.SYNOPSIS
  Bootstrap repo-lead (senior dev) session and print the agent handoff command.

.DESCRIPTION
  Run when you walk away. Uses .autopilot/runtime.json (cursor | claude-code).
  Paste the printed AGENT COMMAND into Cursor Agent or Claude Code.

.EXAMPLE
  .\scripts\start-repo-lead.ps1
  .\scripts\start-repo-lead.ps1 -Runtime claude-code
#>
param(
    [string]$TaskSlug = "network-trust-registry",
    [int]$LoopMinutes = 45,
    [ValidateSet("cursor", "claude-code", "")]
    [string]$Runtime = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

if ($Runtime) {
    & $py -m orchestrator runtime $Runtime | Out-Null
}

$runtimeLine = & $py -m orchestrator runtime 2>&1 | Select-String "^runtime:" | ForEach-Object { $_.Line }
$activeRuntime = "cursor"
if ($runtimeLine -match "runtime:\s*(\S+)") {
    $activeRuntime = $Matches[1]
}

$taskJson = "docs\autopilot\$TaskSlug\$TaskSlug.json"
$taskJsonPosix = "docs/autopilot/$TaskSlug/$TaskSlug.json"
if (-not (Test-Path $taskJson)) {
    Write-Error "Task file not found: $taskJson"
}

Write-Host "==> agent runtime: $activeRuntime"
Write-Host "==> verify.ps1 (baseline)"
powershell -File scripts\verify.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Verify failed - senior dev will fix first. Continuing handoff."
}

Write-Host "==> autopilot use $TaskSlug"
& $py -m orchestrator autopilot use $taskJson
& $py -m orchestrator autopilot status
& $py -m orchestrator autopilot next

$common = (
    "You are ""it"" - senior dev, final product owner. " +
    "Read docs/PRODUCTION_READINESS.md and docs/autopilot/REPO_LEAD_LOOP_PROMPT.md completely. " +
    "Human walked away - ship until SINGULR_PRODUCTION_READY or REPO_LEAD_BLOCKED. " +
    "Bootstrap: autopilot status, next, TDD, verify.ps1, verify, complete, next (same turn). " +
    "No autopilot task? Self-assign per PRODUCTION_READINESS.md. " +
    "After each build session, when blocked, or production-ready: overwrite tasks/HANDOFF_SUMMARY.md " +
    "(work done, verify status, decisions, questions for owner). " +
    "No questions mid-iteration unless blocked."
)

if ($activeRuntime -eq "claude-code") {
    $agentCommand = (
        "IT handoff (Claude Code): Run /sandbox first for autonomous work. " +
        "Read CLAUDE.md and docs/autopilot/CLAUDE-CODE-AUTOPILOT.md. " +
        $common + " " +
        "Run: autopilot $taskJsonPosix OR python -m orchestrator autopilot use/status/next/verify/complete."
    )
    $targetLabel = "CLAUDE CODE"
} else {
    $agentCommand = (
        "Run while I'm away — you are ""it"" (senior dev). Ship until SINGULR_PRODUCTION_READY. " +
        "Follow .cursor/rules/away-mode.mdc and senior-singulr-dev skill (no extra loop instructions needed). " +
        $common + " " +
        "Enable auto-run terminal commands."
    )
    $targetLabel = "CURSOR AGENT"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " PASTE INTO $targetLabel (new session)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host $agentCommand
Write-Host ""
Write-Host "Runtime:      $activeRuntime (scripts\set-agent-runtime.ps1)" -ForegroundColor DarkGray
Write-Host "Guide:        docs\AGENT_RUNTIME.md" -ForegroundColor DarkGray
Write-Host "Handoff file: tasks\REPO_LEAD_HANDOFF.txt" -ForegroundColor DarkGray
Write-Host "Stop loop:    .\scripts\stop-overnight-loop.ps1 (overnight @it) or ask Agent to stop tick shell" -ForegroundColor DarkGray
Write-Host "Overnight:    .\scripts\overnight-loop.ps1 -IntervalMinutes 30 + docs\autopilot\IT_LOOP_PROMPT.md" -ForegroundColor DarkGray
Write-Host "Note:         Singulr GitHub Sync task only pushes git — it does not code." -ForegroundColor DarkYellow
Write-Host ""

$outPath = Join-Path $RepoRoot "tasks\REPO_LEAD_AGENT_COMMAND.txt"
Set-Content -Path $outPath -Value $agentCommand -Encoding utf8
Write-Host "Saved: $outPath" -ForegroundColor Green

try {
    Set-Clipboard -Value $agentCommand
    Write-Host "Copied to clipboard." -ForegroundColor Green
} catch {
    Write-Host "Could not copy to clipboard (copy from above or $outPath)." -ForegroundColor Yellow
}
