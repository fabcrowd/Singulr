# PRD: Singulr production hardening

**Status:** In progress (Autopilot)  
**Task file:** `production-hardening.json`  
**Branch target:** `production-hardening`

## Problem

Singulr MVP is feature-complete locally but not gated by CI, not containerized, and the public verify page lacks automated smoke tests. Deploying or onboarding contributors risks regressions.

## Goals

1. **CI** — Every push/PR runs pytest, ruff, and Hardhat compile (same as `scripts/verify.ps1`).
2. **Container** — Dockerfile + docs for running uvicorn in production without baking secrets.
3. **Verify page smoke tests** — FastAPI TestClient covers `/verify` and static assets.

## Non-goals

- reCAPTCHA, IPQualityScore, admin dashboard
- Live Telegram E2E automation
- Multi-tenant SaaS

## Requirements

### R1 — GitHub Actions CI

- Workflow at `.github/workflows/ci.yml`
- Triggers: `push`, `pull_request` on default branch
- Python 3.12, Node 20
- Steps: checkout → pip install `.[dev]` → pytest → ruff → npm ci → hardhat compile
- Caches for pip and npm

### R2 — Production Docker image

- `Dockerfile` exposing port 8000, runs uvicorn
- README Docker section (build/run, env via `-e` or compose)
- No secrets in image layers
- Structural test in `tests/test_dockerfile.py`

### R3 — Verify page smoke tests

- `tests/test_verify_page.py` with TestClient
- `GET /verify` returns 200, references `verify.js`
- `GET /static/verify.css` returns 200

## Success criteria

- `python -m orchestrator autopilot status` shows 3/3 done
- `powershell -File scripts/verify.ps1` passes locally
- CI workflow is valid YAML and mirrors local verify suite

## Workflow (Cursor Autopilot)

```powershell
python -m orchestrator autopilot next
# implement → verify → complete → next
```
