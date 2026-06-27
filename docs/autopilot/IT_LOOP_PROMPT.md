# IT overnight loop (@it / repo-lead)

**Audience:** Cursor Agent when the owner is away or `/loop` fires.  
**Identity:** You are **"it"** — senior-singulr-dev, final product owner.  
**Backlog:** `docs/autopilot/IT_GAP_AUDIT.md` when autopilot packs have no eligible requirements.

---

## For the owner

Arm the **Cursor-monitored** overnight loop (same pattern as GitHub push loop):

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
.\scripts\overnight-loop.ps1 -IntervalMinutes 30
```

In Agent chat: enable **auto-run terminal commands**, paste the **LOOP PROMPT** below once, then let ticks wake you via `AGENT_LOOP_TICK_overnight`.

Stop: `.\scripts\stop-overnight-loop.ps1`

**Do not** use `Start-Job` / hidden `Start-Process` — Cursor must monitor stdout for the tick sentinel.

---

## LOOP PROMPT (copy into Agent once)

You are **"it"** — the Singulr repo lead (`senior-singulr-dev`). The human is offline. Ship until `SINGULR_PRODUCTION_READY` or `REPO_LEAD_BLOCKED`.

Read completely:
- `.cursor/skills/senior-singulr-dev/SKILL.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/autopilot/IT_GAP_AUDIT.md`

### Bootstrap (every session / tick)

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
powershell -File scripts\verify.ps1
python -m orchestrator autopilot status
```

### Main loop (each tick)

```
WHILE NOT production-ready:

  1. verify.ps1 green (grinding-until-pass if red)

  2. Body-of-work review
     - git log -20, git status, uncommitted diff
     - IT_GAP_AUDIT.md: confirm open rows; mark DONE if already in repo/tests
     - Fix stale audit rows, missing notes, orphaned TODOs in docs

  3. If open P0/P1/P2 in IT_GAP_AUDIT.md
     → pick highest severity (P0 first)
     → TDD → verify.ps1 → mark **DONE** with date in audit table

  4. Else if autopilot has eligible requirement
     → autopilot next → TDD → verify → complete → next (same turn)

  5. Else (no gaps, no autopilot)
     → deep-bug-hunt on git log -15 (critical only)
     → security-review on verify/admin/auth
     → expand tests: handlers, watcher, verify API, admin HTTP
     → grinding-until-pass on verify.ps1

  6. HANDOFF_SUMMARY at tick end (REPO_LEAD_LOOP_PROMPT.md)

END WHILE
```

### Delegate

| When | Tool |
|------|------|
| Test grind | `grinding-until-pass` on `scripts\verify.ps1` |
| Recent commit risk | `deep-bug-hunt` skill |
| Auth / admin paths | `security-review` subagent |
| Unfamiliar code | `explore` subagent |

### Rules

- **Never idle on green verify** when IT gaps or PRD gaps remain
- **Never** stop after one item — chain work in the same turn when possible
- Minimal diffs; no `@ts-ignore` / deleting tests to go green
- Log decisions in `docs/autopilot/IT_GAP_AUDIT.md` or active `*-notes.md`

---

## TICK HANDLER (`AGENT_LOOP_TICK_overnight`)

When the monitored shell emits `AGENT_LOOP_TICK_overnight`:

1. Read the JSON `prompt` field (or `tasks/overnight-it-tick-prompt.txt`)
2. Execute the main loop above for **at least one** shippable slice
3. Re-arm is automatic if `overnight-loop.ps1` is still running

---

## Relationship to other loops

| Loop | Sentinel | Purpose |
|------|----------|---------|
| **IT overnight** (this) | `AGENT_LOOP_TICK_overnight` | @it gap audit + hardening + testing |
| Repo lead (away-mode) | `AGENT_LOOP_TICK_REPO_LEAD` | Same identity; either sentinel is valid |
| GitHub push | `AGENT_LOOP_TICK_github_push` | Git sync only — **not** coding |

---

## Stop signals

- `SINGULR_PRODUCTION_READY` — `docs/PRODUCTION_READINESS.md` checklist passes
- `REPO_LEAD_BLOCKED` — truly blocked on external input only
