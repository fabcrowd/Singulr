# Run full Singulr verification suite (Conductor / ship gate)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "==> pytest"
& .\.venv\Scripts\pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> ruff"
& .\.venv\Scripts\ruff check singulr tests orchestrator
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> hardhat compile"
npm run compile --silent
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> hardhat test"
npm run test --silent
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "ALL CHECKS PASSED"
