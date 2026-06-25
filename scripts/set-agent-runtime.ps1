<#
.SYNOPSIS
  Set or show agent runtime: cursor (default) or claude-code.

.EXAMPLE
  .\scripts\set-agent-runtime.ps1
  .\scripts\set-agent-runtime.ps1 cursor
  .\scripts\set-agent-runtime.ps1 claude-code
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("cursor", "claude-code")]
    [string]$Runtime = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

if ($Runtime) {
    & $py -m orchestrator runtime $Runtime
} else {
    & $py -m orchestrator runtime
}
