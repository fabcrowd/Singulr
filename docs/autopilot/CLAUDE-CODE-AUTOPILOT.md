# Claude Code Autopilot (Gens-ai + Singulr bridge)

Use this path when `.autopilot/runtime.json` has `"runtime": "claude-code"`.

Set runtime:

```powershell
.\scripts\set-agent-runtime.ps1 claude-code
```

## Gens-ai vs Singulr bridge

| Gens-ai (native) | Singulr bridge (same task JSON) |
|------------------|----------------------------------|
| `/autopilot init` | `autopilot.json` already in repo root |
| `/prd "feature"` | `docs/autopilot/<name>/<name>.md` |
| `/tasks prd.md` | Hand-authored `<name>.json` or `/tasks` |
| `/sandbox` | Recommended before autonomous runs |
| `autopilot tasks.json` | Runs requirements in Claude Code sessions |
| `autopilot verify` (hooks) | `python -m orchestrator autopilot verify <id>` |
| — | `python -m orchestrator autopilot next` → `tasks/NEXT_TASK.md` |

You may use **either** the Gens-ai `autopilot` CLI **or** the Singulr orchestrator bridge; both read the same JSON under `docs/autopilot/`.

## Quick start

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
.\scripts\set-agent-runtime.ps1 claude-code

# Recommended before long autonomous runs
# In Claude Code: /sandbox

powershell -File scripts\verify.ps1
python -m orchestrator autopilot use docs/autopilot/network-trust-registry/network-trust-registry.json
python -m orchestrator autopilot status
python -m orchestrator autopilot next
# Read tasks/NEXT_TASK.md — implement TDD, then verify + complete
```

Or in Claude Code after `/sandbox`:

```
/autopilot docs/autopilot/network-trust-registry/network-trust-registry.json
```

## Senior dev ("it") handoff

```powershell
.\scripts\start-repo-lead.ps1
```

Paste the printed command into Claude Code. See `docs/autopilot/REPO_LEAD_LOOP_PROMPT.md` and `docs/PRODUCTION_READINESS.md`.

## Per-requirement loop

Same TDD as Cursor:

1. Red — failing tests for acceptance criteria  
2. Green — minimal implementation  
3. Refactor — loops still green  
4. `python -m orchestrator autopilot verify <id>`  
5. `python -m orchestrator autopilot complete <id>`  
6. **Continue** — `next` and implement next req (do not stop at one complete)

## Task packs

| Pack | JSON |
|------|------|
| Network trust registry (active PRD) | `network-trust-registry/network-trust-registry.json` |
| Overnight improve | `overnight-improve/overnight-improve.json` |
| Overnight ops (done) | `overnight-ops/overnight-ops.json` |
| Production hardening (done) | `production-hardening/production-hardening.json` |

## Done signals

- Pack complete: task-specific (`OVERNIGHT_OPS_COMPLETE`, etc.) in pack `LOOP_PROMPT.md`
- Product: `SINGULR_PRODUCTION_READY` per `docs/PRODUCTION_READINESS.md`
- Always: `scripts/verify.ps1` green
