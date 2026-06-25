# Overnight loop prompt (Cursor Autopilot)

Copy everything inside the fenced block into a **new Cursor Agent** chat before you sleep. Leave the machine awake and the chat running (Max Mode / long context recommended).

---

## LOOP PROMPT (copy from here)

You are the Singulr overnight autopilot agent. Work autonomously until all requirements are done or you are blocked.

### Repo

```
C:\Users\daroo\repos\Telegram bot
```

Do **not** use Claude Code CLI or `~/.local/bin/autopilot`. Use **Cursor + Conductor** only.

### Active task

- PRD: `docs/autopilot/overnight-ops/overnight-ops.md`
- Task JSON: `docs/autopilot/overnight-ops/overnight-ops.json`
- Config: `autopilot.json` (pytest, ruff, compileall, hardhat)

If not already active:

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
python -m orchestrator autopilot use docs/autopilot/overnight-ops/overnight-ops.json
```

### Loop (repeat until `autopilot status` shows 6/6 done)

```
WHILE requirements remain with passes != true AND stuck != true:

  1. READ tasks/NEXT_TASK.md
     If missing or stale, run: python -m orchestrator autopilot next

  2. READ docs/autopilot/overnight-ops/overnight-ops.md for context

  3. TDD for the current requirement ONLY:
     RED   — write failing tests covering ALL acceptance criteria
     GREEN — minimal implementation until tests pass
     REFACTOR — simplify if needed; keep green

  4. Run feedback loops:
     .\.venv\Scripts\pytest -q
     .\.venv\Scripts\ruff check singulr tests orchestrator
     npm run compile --silent

  5. Verify requirement:
     python -m orchestrator autopilot verify <req_id>
     If fail → fix and re-verify. Do not skip.

  6. Complete requirement:
     python -m orchestrator autopilot complete <req_id>
     If complete fails → fix until verify passes, then complete again.

  7. Append one line to docs/autopilot/overnight-ops/overnight-ops-notes.md:
     what you did, req id, test count.

  8. python -m orchestrator autopilot next

END WHILE
```

### Rules

- **One requirement per loop iteration** — no scope creep into future reqs.
- **Never commit** `.env`, tokens, or wallet keys. Update `.env.example` only.
- **Never mark complete** without `autopilot verify` passing (full suite).
- On **blocker** (missing secret, ambiguous product decision):
  - `python -m orchestrator autopilot fail <req_id> --reason "..."`
  - Log blocker in notes file
  - Continue to next eligible requirement if any
- Match existing code style: typed Python, pytest, Ruff, FastAPI patterns in `singulr/`.
- Prefer extending existing modules over new abstractions.

### Stuck detection

If the same test error repeats 3 times with no progress, mark `fail`, document root cause in `tasks/lessons.md`, move on.

### Done signal

When `python -m orchestrator autopilot status` shows **6/6 done**, run:

```powershell
powershell -File scripts\verify.ps1
```

Then output exactly:

```
OVERNIGHT_OPS_COMPLETE
```

Followed by a short summary: requirements completed, files touched, any stuck items, suggested manual steps for Telegram live test.

---

## END LOOP PROMPT

---

## Before bed (30 seconds)

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
python -m orchestrator autopilot use docs/autopilot/overnight-ops/overnight-ops.json
python -m orchestrator autopilot next
powershell -File scripts\verify.ps1   # baseline must be green
```

Open **Cursor Agent**, paste the loop prompt, send.

## Morning check

```powershell
python -m orchestrator autopilot status
type docs\autopilot\overnight-ops\overnight-ops-notes.md
git log --oneline -10
powershell -File scripts\verify.ps1
```

Look for `OVERNIGHT_OPS_COMPLETE` in the agent transcript.

## Honest limits

Cursor Agent will **stop** if the chat hits context limits, the machine sleeps, or the session times out. For best results: disable sleep, plug in power, use one long Agent thread, and enable auto-run for terminal commands if available.
