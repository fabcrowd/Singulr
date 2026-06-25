# Overnight improve — bug audit

Deep review of recent overnight-ops work and security surface. Date: 2026-06-25.

## Critical

### C1. Unauthenticated `POST /api/internal/ban`

**Finding:** Any client could persist a ban record without credentials.

**Trigger:** `POST /api/internal/ban` with `{"telegram_user_id": 123}`.

**Impact:** Arbitrary ban rows in DB; downstream matching may block legitimate users.

**Fix:** Require `X-Admin-Key` via shared `require_admin_key` (same as `/api/admin/bans`). Regression test in `tests/test_internal_ban_api.py`.

**Status:** Fixed in req 2.

## High

### H1. Unhandled `TokenRateLimitError` in bot handlers

**Finding:** `create_token` raises after 3 tokens/24h; `start_command` and `on_join_request` do not catch it.

**Trigger:** User requests verification more than 3 times in 24 hours.

**Impact:** Handler exception; joiner may stay restricted without explanation DM.

**Fix:** Defer to req 3/6 — catch, log, notify user.

### H2. Stylometry `check_known_bad` may attribute wrong ban profile

**Finding:** Stylometry loop in matching may compare against incorrect ban when multiple bans exist.

**Trigger:** Multiple bans with stylometry profiles; new user matches secondary profile.

**Impact:** Wrong ban reason / false positive.

**Fix:** Add targeted unit test in req 4/6; verify loop uses per-ban profile.

## Medium

### M1. Rate limit IP from `X-Forwarded-For` without trusted proxy config

**Finding:** `_client_ip` trusts client-supplied header.

**Fix:** `TRUSTED_PROXY` env; req 5.

### M2. Watcher job re-alerts same match every interval

**Finding:** No deduplication in `run_watcher_job`.

**Fix:** Track alerted pairs; req 4.

### M3. Admin API key compare not timing-safe

**Finding:** Plain `!=` comparison on `X-Admin-Key`.

**Fix:** `secrets.compare_digest`; req 5.

### M4. `channel_id` mismatch between `/verify` and join-request flows

**Finding:** `start_command` uses `settings.channel_id`; join uses `request.chat.id`.

**Fix:** Document or unify; low urgency if single-channel deploy.

## Low / watch

- No direct unit tests for `stylometry_hash` (covered indirectly).
- JSON access logs (`LOG_JSON=true`) not integration-tested.

## Summary

| Severity | Count | Fixed this pass |
|----------|-------|-----------------|
| Critical | 1 | 1 |
| High | 2 | 0 (documented) |
| Medium | 4 | 0 (backlog) |

Next autopilot reqs: handler tests (3), watcher tests (4), security hardening (5), top backlog item (6).
