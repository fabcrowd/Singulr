# Cursor Autopilot (Gens-ai task format, no Claude Code CLI)

Use [Gens-ai/autopilot](https://github.com/Gens-ai/autopilot) **task JSON** with **Cursor Agent** and the Singulr Conductor bridge.

## Quick start

```powershell
cd "C:\Users\daroo\repos\Telegram bot"

# Point at a task file (once per feature)
python -m orchestrator autopilot use docs/autopilot/production-hardening/production-hardening.json

# Assign next requirement → writes tasks/NEXT_TASK.md (injected by Cursor sessionStart hook)
python -m orchestrator autopilot next

# In Cursor Agent: implement TDD (red → green → refactor), then:
python -m orchestrator autopilot verify 1
python -m orchestrator autopilot complete 1

# Repeat next / agent / verify / complete until status shows all done
python -m orchestrator autopilot status
```

Or use the wrapper:

```powershell
.\scripts\autopilot-cursor.ps1 next
.\scripts\autopilot-cursor.ps1 status
```

## vs Claude Code `autopilot` bash command

| Claude Code | Cursor (this repo) |
|-------------|-------------------|
| `autopilot tasks.json` | `python -m orchestrator autopilot next` + Agent |
| `/autopilot init` | `autopilot.json` already in repo root |
| `claude` CLI sessions | Cursor Agent + `.cursor/hooks/session-start.js` |

No `claude auth` required.

## Files

- `autopilot.json` — feedback loops (pytest, ruff, compileall, hardhat)
- `.autopilot/active.json` — which task JSON is active
- `docs/autopilot/<feature>/<feature>.json` — requirements
- `tasks/NEXT_TASK.md` — current agent brief (auto-generated)
- `orchestrator/briefs/AP-<id>.md` — copy of brief per requirement

## Adding a new feature

1. Write a PRD markdown under `docs/autopilot/<name>/` (or brainstorm first).
2. Create `<name>.json` with `requirements[]` (see Gens-ai schema/examples).
3. `python -m orchestrator autopilot use docs/autopilot/<name>/<name>.json`
4. Loop `next` → Cursor Agent → `verify` → `complete`.

## Overnight loops

| Loop | Task JSON | Prompt |
|------|-----------|--------|
| Deploy / ops (done) | `overnight-ops/overnight-ops.json` | `overnight-ops/LOOP_PROMPT.md` |
| **Research / test / improve** | `overnight-improve/overnight-improve.json` | `overnight-improve/LOOP_PROMPT.md` |

```powershell
python -m orchestrator autopilot use docs/autopilot/overnight-improve/overnight-improve.json
python -m orchestrator autopilot next
.\scripts\overnight-loop.ps1 -IntervalMinutes 45   # optional wake ticker
```

Paste `docs/autopilot/overnight-improve/LOOP_PROMPT.md` (LOOP PROMPT section) into Agent before sleep.
