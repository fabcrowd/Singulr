## HANDOFF_SUMMARY (2026-06-29 — Cross-device bans + Admin UX overhaul)

**Read this file first.** Then `tasks/lessons.md`, `docs/PRODUCTION_READINESS.md`, and `docs/autopilot/IT_GAP_AUDIT.md`.

---

### Session summary (2026-06-29)

Two full features shipped:

#### 1. Cross-device fingerprint cross-reference (COMPLETE)

**Problem:** `Profile.telegram_user_id` was `UNIQUE` — only one device fingerprint stored per user. Banning on desktop → rejoining on mobile was undetected.

**Solution:** One `Profile` row per `(telegram_user_id, device_type)`.

| File | Change |
|------|--------|
| `singulr/models.py` | Removed `unique=True` from `telegram_user_id`; added `UniqueConstraint("telegram_user_id", "device_type", name="uq_profiles_user_device")` |
| `singulr/db.py` | PostgreSQL migration: drop `profiles_telegram_user_id_key`, create `uq_profiles_user_device` index |
| `singulr/services/reverification.py` | `get_profile(device_type=...)` for device-specific lookup; `get_all_profiles()` returns all rows; `require_reverification` marks ALL device profiles |
| `singulr/services/bans.py` | `record_ban` now iterates ALL profiles and calls `_upsert_ban_for_fingerprint` for each — one ban record per device |
| `singulr/api/verify.py` | Submit handler upserts by `(telegram_user_id, device_type)` instead of overwriting single row |
| `tests/test_cross_device.py` | 8 new tests: dual-device storage, cross-device ban propagation, false-positive guard |

#### 2. Admin UX overhaul — bot prompts and messages (COMPLETE)

**`singulr/services/telegram_actions.py`**
- Added `_humanize_risk_factor()` — 11 internal code names translated to English; scored factors like `keystroke_similarity:0.87` → `"Typing rhythm similarity to banned user: 87%"`
- Ops channel headers: `⏳ PENDING REVIEW — action required`, `🚫 BAN EVASION DETECTED`, `🛑 BLOCKED`
- Log channel headers: `⚠️ ELEVATED RISK`, `🚫 BAN EVASION`, `👁 WATCHER MATCH — possible re-entry`, `✅ VERIFIED`
- Ops buttons: `Permit` → `Approve`, `Deny` → `Deny & Ban`, `More details` → `View Profile`
- Alert body: raw risk factor comma-list replaced with humanized bullet "Signals:" section
- Profile details: removed useless `Channel ID: -1001234567890` line

**`singulr/bot/handlers.py`**
- Callback confirmations: `"Approved user 7001234"` → `"User 7001234 approved — they can now message the channel."`
- Deny: `"Denied user 7001234"` → `"User 7001234 denied and banned from the channel."`
- Ban flow: `"Banned user 7001234 (other/medium)"` → `"User 7001234 permanently banned. Violation: Bot Abuse (high)."`

**`singulr/bot/security_wizard.py`**
- All questions now say `"of 8"` (was hardcoded `"of 5"` for questions 1–5)
- Category buttons: `bot_abuse`, `scam_fraud` → `Bot Abuse`, `Scam Fraud` in both instant-ban and network keyboards
- Social question: `"Social profiling toggles:"` → `"Enable account history and social profile checks?"`
- Social toggles: `"Profiling: ON/OFF"` → `"Account & social checks: ON/OFF"`, `"External API: ON/OFF"` → `"External risk database: ON/OFF"`
- Automation question: removed dev jargon → `"What should happen when a bot or automated browser is detected?"`

**Tests updated:** `test_log_format.py` (risk factor format), `test_bot_ops_workflow.py` ("More details" → "View Profile")

---

### Test state

**276 passed** (`.venv\Scripts\python -m pytest -q`), ruff clean.

Breakdown: 268 baseline + 8 new cross-device tests.

---

### Prior session context (still valid)

All P0-2 through P0-8 were confirmed DONE in the previous session. See `docs/autopilot/IT_GAP_AUDIT.md`.

Security fixes shipped previously:
- M-1: `InternalBanBody` Pydantic model for `/api/internal/ban`
- P1-7: Internal detection fields stripped from client-facing submit responses
- Privacy policy link fixed (`/privacy` route added to `main.py`)

---

### Production bar

**Not** `SINGULR_PRODUCTION_READY`. Remaining mandatory items:

- **Security review** on API/auth/admin paths (skill: `security-review`)
- **Deep bug hunt** on recent commits (skill: `deep-bug-hunt`)
- Confirm `docs/DEPLOY.md` matches current repo (compose, env, health checks)
- **Deploy prerequisites** — next active goal: walk through service signups needed to deploy (Telegram bot token, webhook host, PostgreSQL, FingerprintJS key, etc.)

---

### Next up

The interrupted goal was: **"prompt me through signing up for any services needed to deploy the bot."**

Services needed to deploy (resume from here):

| Service | Purpose | Status |
|---------|---------|--------|
| Telegram bot token | `BOT_TOKEN` env var — create via @BotFather | ❓ check `.env` |
| Public HTTPS host | `PUBLIC_BASE_URL` — webhook target for verify page | ❓ needs domain + TLS |
| PostgreSQL | `DATABASE_URL` for production (SQLite is dev-only) | ❓ needs cloud PG |
| FingerprintJS (optional) | `FINGERPRINT_PUBLIC_KEY` + `FINGERPRINT_SECRET_KEY` | ❓ free tier available |
| Admin ops Telegram group | `ADMIN_OPS_CHAT_ID` — where alerts land | ❓ just create a group |
| Log channel | `LOG_CHANNEL_ID` — audit trail | ❓ just create a channel |

Config reference: `singulr/config.py` (all env vars) and `docs/DEPLOY.md`.

---

### Commands

```powershell
# Test gate
.venv\Scripts\python -m pytest tests\ -q --tb=short

# Lint
.venv\Scripts\ruff check singulr\ tests\

# Orchestrator
python -m orchestrator autopilot status
python -m orchestrator runtime
```

Playbooks: `docs/autopilot/IT_LOOP_PROMPT.md` · `tasks/overnight-it-tick-prompt.txt`
