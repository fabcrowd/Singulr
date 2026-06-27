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

### 2026-06-25 — reinstatement — re-ban after overturn silently failed
- **Symptom:** Admin re-ban left `Ban.status=overturned` while profile showed banned.
- **Root cause:** `record_ban` skipped updates when a ban row already existed.
- **Fix:** Reactivate overturned/expired rows on re-ban; filter `status=active` in matching/watcher.
- **Guard:** `tests/test_reinstatement.py::test_record_ban_reactivates_overturned_row`

### 2026-06-26 — deep-harden — verify double-submit race
- **Symptom:** Concurrent verify submits could both approve the same user.
- **Root cause:** `validate_token` + late `mark_token_used` was not atomic.
- **Fix:** `claim_verification_token()` UPDATE … WHERE used=false at submit entry.
- **Guard:** `tests/test_hardening.py::test_claim_token_prevents_second_submit`, `tests/test_api_verify.py::test_submit_rejects_reused_token`

### 2026-06-26 — deep-harden — legacy approve_/ban_ callbacks
- **Symptom:** WATCHER_MATCH log-channel Approve/Ban buttons usable by any member.
- **Root cause:** `on_callback` only gated permit/deny/details, not `approve_` / `ban_*`.
- **Fix:** `_require_ops_admin()` on approve_, ban_, ban_cat_, ban_sev_ paths.
- **Guard:** `tests/test_hardening.py::test_approve_callback_rejects_non_admin`

### 2026-06-26 — overnight-loop — stale deep-harden prompt
- **Symptom:** Overnight ticks fired but agent did no work; prompt still referenced deep-harden pack (5/5 done).
- **Root cause:** Inline loop body never updated after autopilot packs completed; no IT gap audit directive.
- **Fix:** `docs/autopilot/IT_LOOP_PROMPT.md`, `tasks/overnight-it-tick-prompt.txt`, foreground `scripts/overnight-loop.ps1` (Cursor-monitored); away-mode + REPO_LEAD TICK handler point at IT_GAP_AUDIT.
- **Guard:** Re-arm with `.\scripts\overnight-loop.ps1`; stop old inline loop via `.\scripts\stop-overnight-loop.ps1` or kill stale shell.

---
