# Deep-harden audit

**Scope:** Uncommitted diff + social profiling / verify / bot callback paths (2026-06-25)

## Critical

### C1 — Double verify submit race (FIXED)

**Impact:** Two concurrent `POST /api/verify/submit` with the same token could both pass `validate_token` before either called `mark_token_used`, causing duplicate bot notifications and possible double approve.

**Trigger:** User double-taps submit or parallel requests within the matching window.

**Fix:** `claim_verification_token()` atomically sets `used=True` via `UPDATE … WHERE used=false` before processing. Submit uses claim at entry; precheck still uses read-only validate.

**Test:** `tests/test_hardening.py::test_claim_token_prevents_second_submit`

## High

### H1 — Admin ops callbacks lacked authorization (FIXED)

**Impact:** Any Telegram user who could tap inline buttons in the ops channel (or forward messages) could trigger permit/deny/details for arbitrary user ids.

**Fix:** `_require_ops_admin()` checks `get_chat_member` status is administrator/creator before permit, deny, and details callbacks.

**Test:** `tests/test_hardening.py::test_permit_callback_rejects_non_admin`

### H2 — External API malformed JSON could crash provider stack (FIXED)

**Impact:** `response.json()` or bad `risk_score` types could raise uncaught exceptions.

**Fix:** Parse with `json.loads`, catch `ValueError`/`TypeError`, raise `SocialProfileProviderError` for fail-open/fail-closed policy handling.

**Test:** `tests/test_social_external.py::test_external_api_provider_raises_on_malformed_json`

## Medium (watch)

- **Expired token claim:** Claim marks `used=True` before expiry re-check; expired tokens become consumed without processing (acceptable one-shot semantics).

### M1 — Legacy approve_/ban_ callbacks lacked admin check (FIXED)

**Impact:** WATCHER_MATCH log-channel Approve/Ban buttons could be used by any member who saw the message.

**Fix:** `_require_ops_admin()` on `approve_`, `ban_`, `ban_cat_`, and `ban_sev_` handlers.

**Test:** `tests/test_hardening.py::test_approve_callback_rejects_non_admin`

## Low / no action

- Style and copy nits in wizard question numbering.
- Theoretical blocklist file TOCTOU on reload (acceptable for v1).

## Summary

**1 critical and 2 high issues fixed with regression tests.** No open critical findings after fixes.
