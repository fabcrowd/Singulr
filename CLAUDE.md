# Claude Code — Singulr

You are in the **Singulr** Telegram bot repo. Check agent runtime first:

```powershell
python -m orchestrator runtime
```

If not `claude-code`, the owner may be on Cursor — still follow `AGENTS.md` and task JSON.

## Claude Code autopilot

1. Read [docs/autopilot/CLAUDE-CODE-AUTOPILOT.md](docs/autopilot/CLAUDE-CODE-AUTOPILOT.md)
2. Before long autonomous work: **`/sandbox`**
3. Run tasks: `autopilot docs/autopilot/<feature>/<feature>.json`  
   **or** bridge: `python -m orchestrator autopilot use/status/next/verify/complete`
4. Quality gate: `powershell -File scripts\verify.ps1`

## Senior dev handoff ("it")

- Full loop: [docs/autopilot/REPO_LEAD_LOOP_PROMPT.md](docs/autopilot/REPO_LEAD_LOOP_PROMPT.md)
- Production bar: [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)
- Start command: `.\scripts\start-repo-lead.ps1`

## Shared conventions

- [AGENTS.md](AGENTS.md) — TDD, gotchas, learnings
- `tasks/NEXT_TASK.md` — current autopilot requirement (orchestrator `next`)
- `tasks/lessons.md` — do not repeat past failures
- Never commit `.env` or secrets

## Switching back to Cursor

```powershell
.\scripts\set-agent-runtime.ps1 cursor
```

See [docs/AGENT_RUNTIME.md](docs/AGENT_RUNTIME.md).
