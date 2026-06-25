param(
    [Parameter(Position = 0)]
    [string]$Command = "status",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$map = @{
    "use"      = @("autopilot", "use")
    "status"   = @("autopilot", "status")
    "next"     = @("autopilot", "next")
    "verify"   = @("autopilot", "verify")
    "complete" = @("autopilot", "complete")
    "fail"     = @("autopilot", "fail")
}

if (-not $map.ContainsKey($Command)) {
    Write-Host "Usage: autopilot-cursor.ps1 <use|status|next|verify|complete|fail> [args]"
    exit 1
}

$argsList = $map[$Command] + $Rest
& $py -m orchestrator @argsList
exit $LASTEXITCODE
