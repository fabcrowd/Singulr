<#
.SYNOPSIS
  Commit and push local repo changes to GitHub when there is work to sync.

.DESCRIPTION
  Stages tracked and untracked files (respecting .gitignore), skips when clean,
  refuses to commit .env, and pushes the current branch to origin.

.PARAMETER DryRun
  Show what would be committed without creating a commit or pushing.

.EXAMPLE
  .\scripts\sync-to-github.ps1
#>
param(
    [switch]$DryRun,
    [string]$TargetBranch = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$LogFile = Join-Path $RepoRoot ".autopilot\github-sync.log"

function Write-SyncLog {
    param([string]$Message)
    $line = "$(Get-Date -Format o) $Message"
    New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

Set-Location $RepoRoot

if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    Write-SyncLog "ERROR: not a git repository ($RepoRoot)"
    exit 1
}

$status = git status --porcelain
if (-not $status) {
    Write-SyncLog "SKIP: working tree clean"
    exit 0
}

if ($DryRun) {
    Write-SyncLog "DRY-RUN: would sync the following:"
    $status | ForEach-Object { Write-SyncLog "  $_" }
    exit 0
}

git add -A

$staged = @(git diff --cached --name-only)
if ($staged.Count -eq 0) {
    Write-SyncLog "SKIP: no committable changes after git add"
    exit 0
}

$blocked = $staged | Where-Object { $_ -eq ".env" -or $_ -like ".env.*" }
if ($blocked) {
    git reset HEAD -- $blocked | Out-Null
    Write-SyncLog "WARN: unstaged secret file(s): $($blocked -join ', ')"
    $staged = @(git diff --cached --name-only)
    if ($staged.Count -eq 0) {
        Write-SyncLog "SKIP: only blocked secret files changed"
        exit 0
    }
}

$branch = git branch --show-current
if (-not $branch) {
    Write-SyncLog "ERROR: detached HEAD; refusing to commit"
    exit 1
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
$message = "chore: sync local work $stamp"
git commit -m $message | ForEach-Object { Write-SyncLog $_ }

$pushBranch = if ($TargetBranch) { $TargetBranch } else { $branch }
Write-SyncLog "PUSH: origin HEAD -> $pushBranch (local branch: $branch)"
git push origin "HEAD:$pushBranch" 2>&1 | ForEach-Object { Write-SyncLog $_ }

if ($LASTEXITCODE -ne 0) {
    Write-SyncLog "ERROR: push failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-SyncLog "OK: synced $($staged.Count) path(s) to origin/$pushBranch"
exit 0
