# Agent runtime (Cursor vs Claude Code)

This repo supports **two agent hosts** with the **same** task JSON, PRDs, and quality gate (`scripts/verify.ps1`).  
Switch runtime locally — do not fork the codebase.

## Set runtime (one command)

```powershell
cd "C:\Users\daroo\repos\Telegram bot"

# Cursor (default)
.\scripts\set-agent-runtime.ps1 cursor

# Claude Code + Gens-ai autopilot
.\scripts\set-agent-runtime.ps1 claude-code
```

Stored in `.autopilot/runtime.json` (safe to commit; change per machine if you use both).

Check:

```powershell
.\scripts\set-agent-runtime.ps1
# or
python -m orchestrator runtime
```

## Shared (both runtimes)

| Piece | Location |
|-------|----------|
| Task JSON | `docs/autopilot/<feature>/<feature>.json` |
| PRDs | `docs/autopilot/<feature>/<feature>.md` |
| Active task | `.autopilot/active.json` |
| Next requirement | `tasks/NEXT_TASK.md` |
| Orchestrator CLI | `python -m orchestrator autopilot use\|status\|next\|verify\|complete` |
| Verify gate | `powershell -File scripts\verify.ps1` |
| Production bar | `docs/PRODUCTION_READINESS.md` |
| Senior dev role | Repo lead = **"it"** — `docs/autopilot/REPO_LEAD_LOOP_PROMPT.md` |
| Handoff | `.\scripts\start-repo-lead.ps1` |

## Cursor

| Piece | Location |
|-------|----------|
| Docs | [docs/autopilot/CURSOR-AUTOPILOT.md](autopilot/CURSOR-AUTOPILOT.md) |
| Skills | `.cursor/skills/senior-singulr-dev/` |
| Rules | `.cursor/rules/autopilot.mdc` |
| Session hook | `.cursor/hooks/session-start.js` |
| Long runs | Cursor `/loop` + `scripts/start-repo-lead.ps1` |
| Do **not** use | Claude Code `~/.local/bin/autopilot` as the task runner |

## Claude Code

| Piece | Location |
|-------|----------|
| Project instructions | [CLAUDE.md](../CLAUDE.md) (repo root) |
| Docs | [docs/autopilot/CLAUDE-CODE-AUTOPILOT.md](autopilot/CLAUDE-CODE-AUTOPILOT.md) |
| Gens-ai commands | `/sandbox`, `/autopilot`, `/prd`, `/tasks` (after skill install) |
| Native runner | `autopilot docs/autopilot/<feature>/<feature>.json` |
| Bridge (optional) | Same `python -m orchestrator autopilot *` for `NEXT_TASK.md` |
| Learnings | `AGENTS.md`, `tasks/lessons.md` |

## GitHub upload

1. Push repo as-is; default runtime is `cursor`.
2. On a machine using Claude Code: `.\scripts\set-agent-runtime.ps1 claude-code`
3. Reinstall [Gens-ai/autopilot](https://github.com/Gens-ai/autopilot) skills in Claude Code per their docs.
4. Both paths use the same `autopilot.json` feedback loops at repo root.

## Senior dev handoff (either runtime)

```powershell
.\scripts\start-repo-lead.ps1
```

Prints the correct paste command for your active runtime and copies it to the clipboard.
