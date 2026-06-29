# Bug Research Report — Ban Evasion Detection

**Date:** 2026-06-28  
**Scope:** All critical paths in the ban-evasion detection pipeline  
**Verdict: No critical security bugs found.** Two medium findings fixed inline; known design limitations documented below.

---

## Critical (severity: crash / auth bypass / data loss)

**None found.**

The HMAC challenge proof correctly binds `challengeSecret + token + visitorId` such that a forged visitor_id at submit is rejected with 400 `challenge_invalid`. The atomic `UPDATE WHERE used=False` token claim prevents double-submission races.

---

## Medium — Fixed

### M-1: `/api/internal/ban` — no input validation → unhandled 500

**File:** `singulr/api/verify.py` — `@router.post("/api/internal/ban")`  
**Root cause:** `payload: dict[str, Any]`; `int(payload["telegram_user_id"])` raises `KeyError` (missing key) or `ValueError` (bad type) → 500, not 422.  
**Fix:** Replaced raw dict with a Pydantic `InternalBanBody` model (same file).  
**Blast radius:** Low — requires valid `ADMIN_API_KEY`; external attacker already has full admin access if they have this key.

---

## Low (documented, not fixed)

### L-1: Manual bans on users who never verified → no device fingerprint on ban record

**Detail:** `record_ban` looks up `Profile.fingerprint_hash` for the user. If the user was manually banned from the ops channel before completing any verify flow, their `Profile` row may not exist. In that case, `record_ban` falls back to `hash_fingerprint(str(telegram_user_id))` — a pseudo-fingerprint derived from the Telegram user ID, not the browser.

**Impact:** If such a user creates a new Telegram account and rejoins, neither the exact-fingerprint check nor keystroke matching will find a device match. The `telegram_user_id` exact check also misses because it's a new account.

**Mitigation:** This scenario only applies to users banned manually (ops channel) before they ever touched the verify page. Any user who completed at least one verification has a real Profile with a real browser fingerprint. All automated (verify-flow) bans have the real fingerprint.

**Recommendation (post-launch):** Surface a "link fingerprint" admin action in the ops channel that lets admins manually associate a fingerprint with a ban record when the user's Profile exists.

### L-2: Ban taxonomy maps ban-evasion to `BanCategory.OTHER`

**File:** `singulr/services/verify_ban.py`  
**Detail:** Ban evasion detections (keystroke/stylometry match to a banned record) produce `BanCategory.OTHER` with no dedicated enum value.  
**Impact:** Analytics can't distinguish "banned because new spam" from "banned because device re-entry." Cross-channel network score weighting may underweight evasion records.  
**Recommendation:** Add `BanCategory.BAN_EVASION` in a future taxonomy patch.

---

## Info (not actionable for ship)

### I-1: Precheck runs `check_known_bad` with fallback fingerprint then again with real fingerprint

The client sends precheck twice: once with the fallback hash, once with the FingerprintJS ID. The server runs `check_known_bad` both times. This is correct behavior (catches ban at either call) but doubles DB load per new joiner. At low scale this is fine; at high scale, cache the first result for 60s.

### I-2: `claim_verification_token` marks token used before checking expiry

The UPDATE runs first (atomically marking `used=True`), then the application checks expiry. An expired token that was unused gets permanently consumed (correct — expired tokens should not be retried). The caller gets 410 `link_expired`. This is correct behavior, documented here to avoid confusion in future tests.

### I-3: FingerprintJS fallback (`fb_` prefix) is weaker than OSS / Pro

A determined attacker who disables FingerprintJS can cycle fallback fingerprints by clearing browser state + UA spoofing. The HMAC still binds their submitted visitor_id to the precheck session, so they can't swap fingerprints mid-flow — but across fresh joins, the fallback provides little continuity. Operators who need high confidence should set `FINGERPRINT_PUBLIC_KEY` for FingerprintJS Pro.

---

## Security model summary

| Attack | Defended? | How |
|--------|-----------|-----|
| Submit forged visitor_id | Yes | HMAC proof binds visitor_id to precheck secret |
| Replay same token on new account | Yes | Token claimed atomically; one-use |
| Bypass precheck with fresh fallback fingerprint | Partial | HMAC ties it to one precheck session; cross-session fallback is weak |
| New Telegram account, same device | Yes (if prior ban has fingerprint) | `ban_by_fp` + keystroke similarity |
| New Telegram account, same typing pattern | Yes | Keystroke similarity threshold |
| New account, same writing style post-join | Yes | Stylometry watcher |
| Admin without ADMIN_API_KEY | Yes | 503 when key unset; 401 on wrong key |
| Rate limit bypass on precheck | Yes | Per-IP + per-token limits |
