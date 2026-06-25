#!/usr/bin/env bash
# Run full Singulr verification suite (for Ralph loops)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> pytest"
.venv/bin/pytest -q

echo "==> ruff"
.venv/bin/ruff check singulr tests

echo "==> hardhat compile"
npm run compile --silent

echo "ALL CHECKS PASSED"
