# Agent guidelines (Singulr)

Global conventions for **Cursor** and **Claude Code** agent runs. Runtime: `docs/AGENT_RUNTIME.md` · `python -m orchestrator runtime`. Append learnings under **Gotchas** after corrections.

## TDD (autopilot requirements)

1. **Red** — Tests cover every `acceptance` criterion; confirm failure before implementing.
2. **Green** — Minimal code until feedback loops pass.
3. **Refactor** — Simplify; re-run typecheck/tests/lint from `autopilot.json`.
4. **One requirement per iteration** — verify → complete → `autopilot next` → **start the next req in the same turn**. Do not end the turn after a single complete unless blocked or session is done.

## Feedback loops (from `autopilot.json`)

Run sequentially; do not commit if any fail:

```powershell
.\.venv\Scripts\python -m compileall -q singulr orchestrator
.\.venv\Scripts\pytest -q
.\.venv\Scripts\ruff check singulr tests orchestrator
npm run compile --silent
```

Or: `powershell -File scripts\verify.ps1`

## Search before implementing

- Reuse `singulr/services/*`, `tests/conftest.py` fixtures.
- Bot patterns: read `singulr/bot/handlers.py` and existing API tests before new handler tests.
- Never commit `.env`; update `.env.example` only.

## Gotchas

- 2026-06-25: **Stopping early is a failure mode.** No tasks ≠ done. Self-assign from PRD / next pack / `PRODUCTION_READINESS.md`. Only `SINGULR_PRODUCTION_READY` ends the job.
- 2026-06-25: **Do not stop after one `complete`.** Run `autopilot next` and keep shipping in the same turn. Session summaries mid-backlog caused overnight runs to stall at 5/14 reqs.
- 2026-06-25: Do not add `test_overnight_audit.py` / `test_overnight_report.py` until their requirements run — full `pytest` runs on every `autopilot verify` and will block earlier reqs.
- 2026-06-25: `POST /api/internal/ban` now requires `X-Admin-Key` (shared `singulr.api.security.require_admin_key`).

## Repo lead (overnight handoff)

**Start senior dev:** `.\scripts\start-repo-lead.ps1` → paste into **Cursor Agent** or **Claude Code** (command matches `.autopilot/runtime.json`).  
When the owner is away, **senior-singulr-dev** / **"it"** owns the **final product**. Stop only at `docs/PRODUCTION_READINESS.md` (`SINGULR_PRODUCTION_READY`). Handoff details: `docs/autopilot/REPO_LEAD_LOOP_PROMPT.md`.
