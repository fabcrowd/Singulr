<#
.SYNOPSIS
  Run one autopilot requirement iteration (Gens-ai --batch 1 equivalent for Cursor).

.DESCRIPTION
  Assigns NEXT_TASK, prints status, and reminds Agent to run verify/complete after TDD.

.EXAMPLE
  .\scripts\cursor-autopilot-batch.ps1
  .\scripts\cursor-autopilot-batch.ps1 -VerifyOnly -ReqId 2
#>
param(
    [switch]$VerifyOnly,
    [string]$ReqId = "",
    [switch]$Complete
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

if ($VerifyOnly -and $ReqId) {
    & $py -m orchestrator autopilot verify $ReqId
    if ($Complete -and $LASTEXITCODE -eq 0) {
        & $py -m orchestrator autopilot complete $ReqId
        & $py -m orchestrator autopilot next
    }
    exit $LASTEXITCODE
}

& $py -m orchestrator autopilot status
Write-Host ""
& $py -m orchestrator autopilot next
Write-Host ""
Write-Host "Implement tasks/NEXT_TASK.md (red -> green -> refactor), then:"
Write-Host "  .\scripts\cursor-autopilot-batch.ps1 -VerifyOnly -ReqId <id> -Complete"
Write-Host "Or read docs/autopilot/overnight-improve/LOOP_PROMPT.md for full overnight loop."
