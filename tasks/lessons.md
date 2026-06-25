# Orchestrator lessons

Failures and patterns the agent must not repeat. Updated automatically on `orchestrator fail` and manually after corrections.

## Format

```
### YYYY-MM-DD — TASK_ID — short title
- **Symptom:** what broke
- **Root cause:** why
- **Fix:** what worked
- **Guard:** test or check that prevents recurrence
```

### 2026-06-25 — overnight-loop — agent stopped after each complete
- **Symptom:** Overnight run shipped 5/14 reqs then stopped; user expected continuous iteration.
- **Root cause:** Agent treated each `complete` as session end; `/loop` not armed; session-start hook said "one requirement per session".
- **Fix:** Docs/hooks now require complete → next → continue in same turn; `/loop` must use background ticker skill.
- **Guard:** `AGENTS.md` Gotcha; `session-start.js` and `autopilot.mdc` rules updated.

### 2026-06-25 — senior-dev — stopping before production-ready
- **Symptom:** Agent treated empty autopilot queue or partial pack progress as "done".
- **Root cause:** No production readiness bar; stop signal was "task file complete".
- **Fix:** `docs/PRODUCTION_READINESS.md`; stop only at `SINGULR_PRODUCTION_READY`; self-assign when no tasks.
- **Guard:** senior-singulr-dev skill + REPO_LEAD_LOOP_PROMPT + session-start hook.

### 2026-06-25 — away-mode — loop did not wake agent
- **Symptom:** Owner thought dev ran all day; only hourly `chore: sync local work` commits; backlog stuck at 7/14.
- **Root cause:** Agent used `Start-Process -WindowStyle Hidden` for `/loop` instead of Cursor monitored Shell + `notify_on_output`; owner also had Singulr GitHub Sync scheduled task (git only).
- **Fix:** `.cursor/rules/away-mode.mdc`; senior-singulr-dev away checklist; REPO_LEAD_LOOP_PROMPT owner table; start-repo-lead simplified prompt.
- **Guard:** Forbidden table in away-mode.mdc; never substitute overnight-autopilot-loop.ps1 or github sync for coding.

---
