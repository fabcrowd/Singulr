# Overnight improve loop (Cursor Autopilot + subagents)

Copy the **LOOP PROMPT** block into a **new Cursor Agent** chat before sleep. Leave the machine awake, auto-run terminal commands enabled, Max Mode recommended.

Optional: start the shell ticker (wakes Agent every 45 minutes):

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
.\scripts\overnight-loop.ps1 -IntervalMinutes 45
```

Stop: `.\scripts\stop-overnight-loop.ps1`

---

## LOOP PROMPT (copy from here)

You are the Singulr **overnight improve** agent. Research, test, and improve this repo autonomously until all autopilot requirements are done or you are blocked.

### Repo

```
C:\Users\daroo\repos\Telegram bot
```

Use **Cursor + Conductor autopilot** only (not Claude Code `~/.local/bin/autopilot`).

### Activate (once per session)

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
python -m orchestrator autopilot use docs/autopilot/overnight-improve/overnight-improve.json
python -m orchestrator autopilot status
python -m orchestrator autopilot next
```

PRD: `docs/autopilot/overnight-improve/overnight-improve.md`  
Task JSON: `docs/autopilot/overnight-improve/overnight-improve.json`  
Notes: `docs/autopilot/overnight-improve/overnight-improve-notes.md`

### Skills & subagents (use proactively)

| When | What |
|------|------|
| Req 1, test gaps | **parallel-exploring** or multiple **explore** subagents (bot, services, tests) |
| Req 2, every 3rd tick | **deep-bug-hunt** skill on recent commits |
| Req 3 | **telegram-bot-architect** skill for handler tests |
| Req 5 | **security-review** subagent on branch/uncommitted diff |
| After any code change | **grinding-until-pass** until pytest + ruff + compile green |
| Stuck on same failure 3× | **grinding-until-pass** with narrower scope |

Launch subagents **in parallel** when areas are independent (e.g. bot handlers + watcher + security).

### Main loop (one requirement OR one tick per iteration)

```
WHILE autopilot status shows requirements with passes != true AND stuck != true:

  1. READ tasks/NEXT_TASK.md
     If missing: python -m orchestrator autopilot next

  2. READ the requirement's TDD section in overnight-improve.json

  3. RESEARCH (req 1–2 only, or when blocked):
     - Task tool explore/parallel-exploring: "untested singulr modules", "verify API risks", "bot handler flows"
     - Consolidate into docs/autopilot/overnight-improve/research.md or audit.md

  4. TDD for current requirement ONLY:
     RED   → failing tests for ALL acceptance criteria
     GREEN → minimal implementation
     REFACTOR → simplify; keep green

  5. Feedback loops:
     .\.venv\Scripts\pytest -q
     .\.venv\Scripts\ruff check singulr tests orchestrator
     npm run compile --silent

  6. Verify + complete:
     python -m orchestrator autopilot verify <req_id>
     python -m orchestrator autopilot complete <req_id>

  7. Append line to overnight-improve-notes.md (req id, tests added, subagents used)

  8. python -m orchestrator autopilot next

END WHILE
```

### TICK HANDLER (when `AGENT_LOOP_TICK_overnight_improve` fires)

1. `python -m orchestrator autopilot status`
2. If pending requirement → run **one** full iteration (steps 1–8 above)
3. Else if suite not green → **grinding-until-pass** on `scripts\verify.ps1`
4. Else → launch **deep-bug-hunt** on `git log --oneline -15`; file findings in `audit.md`; fix critical only
5. Re-arm is automatic via `overnight-loop.ps1`

### Rules

- **One requirement per iteration** unless grinding a single failing test
- **Never commit** `.env` or secrets; `.env.example` only
- **Never** `autopilot complete` without `autopilot verify` passing
- Blocker → `python -m orchestrator autopilot fail <id> --reason "..."` + note in `tasks/lessons.md`
- Match repo style: typed Python, pytest, Ruff, FastAPI patterns
- Prefer minimal diffs; no Phase 2 features

### Stuck detection

Same test error 3× with no progress → `fail`, document in `tasks/lessons.md`, pick next eligible req.

### Done signal

When status shows **7/7 done**:

```powershell
powershell -File scripts\verify.ps1
```

Output exactly:

```
OVERNIGHT_IMPROVE_COMPLETE
```

Then summarize: requirements done, tests added, bugs fixed, subagents used, manual Telegram steps.

---

## END LOOP PROMPT

---

## Before bed (~1 min)

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
python -m orchestrator autopilot use docs/autopilot/overnight-improve/overnight-improve.json
python -m orchestrator autopilot next
powershell -File scripts\verify.ps1
.\scripts\overnight-loop.ps1 -IntervalMinutes 45
```

Paste **LOOP PROMPT** into Agent and send.

## Morning check

```powershell
python -m orchestrator autopilot status
type docs\autopilot\overnight-improve\overnight-improve-notes.md
type docs\autopilot\overnight-improve\IMPROVE_REPORT.md
git log --oneline -15
powershell -File scripts\verify.ps1
```

Look for `OVERNIGHT_IMPROVE_COMPLETE` in the agent transcript.

## Honest limits

Cursor stops if the machine sleeps, context fills, or the session times out. Disable sleep, stay on power, one long Agent thread, auto-run terminals on.
