# Overnight improve — implementation log

## 2026-06-25 — Req 6

**Backlog item:** #2 Unhandled `TokenRateLimitError` in `start_command` (research.md)

**Change:** `singulr/bot/handlers.py` — catch `TokenRateLimitError` in `/start` and `/verify` entry path; reply with the same user-facing message as `on_join_request`.

**Also:** `singulr/api/security.py` — `secrets.compare_digest` for admin API key comparison (research #6, minimal hardening).

**Tests:** `tests/test_bot_handlers.py::test_start_command_handles_token_rate_limit`

**Verify:** `scripts/verify.ps1` green (141+ tests).
