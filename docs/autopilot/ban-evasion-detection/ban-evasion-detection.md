# PRD: Ban-Evasion Detection — Ship Checklist

**Feature:** Singulr core detection pipeline — fingerprint + keystroke + social profiling + watcher  
**Target ship:** 2026-06-29 (tomorrow morning)  
**Status:** Implementation complete (phases 1–4 shipped 2026-06-25). This PRD is a ship-checklist: it documents what is built, what is still untested, and the exact remaining work to reach `SINGULR_PRODUCTION_READY`.

---

## 1. Introduction / Overview

**Problem:** When a Telegram channel admin bans a malicious user, that user can create a new Telegram account with a new phone number and rejoin within seconds. Phone numbers and usernames provide zero continuity between accounts.

**Solution:** Singulr detects re-entry by fingerprinting the *device* and *typing behaviour* — signals that persist across new SIMs, accounts, and usernames. A user who was banned on account A will be caught when they rejoin on account B if they use the same device or type in the same way.

**Detection layers (all shipped):**

| Layer | Signal | Persists across new account? |
|-------|--------|------------------------------|
| Device fingerprint | FingerprintJS (Pro/OSS) + fallback hash | Yes — same device |
| Keystroke dynamics | Timing profile from verify sentence | Yes — same person |
| Stylometry | Writing-style vector (Watcher post-join) | Yes — same person |
| Social heuristics | Telegram username/name patterns | Partial — catches laziness |
| Chain registry | On-chain fingerprint blacklist (optional) | Yes — cross-channel |

---

## 2. Goals

1. **Catch device re-entry:** A banned user on the same device is blocked or flagged before gaining channel access, even with a new Telegram account and phone number.
2. **Catch typing-pattern re-entry:** High keystroke or stylometry similarity to a banned user triggers PENDING or BLOCK.
3. **Admin transparency:** All evidence (fingerprint match, keystroke score, social signals) is visible in the ops channel card and "More details" button.
4. **Fail safe:** Any detection layer failure (API timeout, chain RPC down) never blocks a clean user; it produces PENDING for human review.
5. **Zero joiner friction:** Detection is invisible — no extra fields, no "connect socials," no error messages beyond "Account restricted."

---

## 3. User Stories

### Joiner (malicious re-entrant)
> As a banned user attempting to rejoin on a new account, I click the join button and receive a verification link. I complete the form honestly. Because my device fingerprint matches a banned record, I am silently blocked and see only "Account restricted."

### Joiner (new legitimate member)
> As a genuine new member, I click join, receive a link, type the verification sentence, and receive channel access within seconds. The process feels like a routine step.

### Channel admin
> As an admin, I see a pending join in the ops channel. I click "More details" and see: fingerprint hash, keystroke score, social signals, and full ban history. I click Permit or Deny.

### Cross-channel admin (network registry)
> As an admin of a sister channel, a joining user who was banned elsewhere is flagged as PENDING with reason "cross-channel network history." I review with full context.

---

## 4. Requirements

### Functional

**F1. Join gate (shipped)**
- On `ChatJoinRequest`, bot restricts user and DMs a time-limited verify link (~10 min TTL).
- One active link per user; new join request invalidates previous token.
- Join-time snapshot (username, display_name, language_code, channel_title) stored on `VerificationToken`.

**F2. Verify page (shipped)**
- Precheck call: rate limit, token validity, returns sentence + HMAC challenge secret.
- Client captures: FingerprintJS visitor_id (Pro → OSS → fallback), keystroke events (down/up timing, flight time), WPM, error count, env_flags (webdriver, headless UA, WebGL renderer, plugin count, outer dims).
- Submit: HMAC proof, all signals to `/api/verify/submit`.
- States shown: loading, blocked, pending, success, error — never exposes reason for block.

**F3. Matching pipeline (shipped)**
- Order: exact user_id ban → exact fingerprint ban → chain blacklist → network reputation → IP velocity → env anomaly → automation score → keystroke similarity → stylometry similarity → social profiling → APPROVE.
- Keystroke and stylometry similarity each produce BLOCK (≥ threshold) or PENDING (≥ flag threshold) or no effect.
- Social profiling: hard category in `instant_ban_categories` → BLOCK; risk_score ≥ threshold (default 40) → PENDING.
- All BLOCK outcomes trigger `persist_ban` + Telegram channel ban + ops notification.

**F4. Social profiling (shipped)**
- TelegramNativeProvider: no_username, suspicious username patterns, empty_display_name, display_name_brand_overlap.
- BlocklistProvider: self-hosted JSON list of known bad `telegram_user_id`s.
- ExternalApiProvider: optional per-channel opt-in; 1.5s timeout; sends user_id + username + display_name only.
- Composite provider merges results; fail_open (default) or fail_closed per channel policy.
- Token-row cache prevents double-billing on More details + submit.

**F5. Admin ops path (shipped)**
- Every verify outcome → ops channel card with: user info, decision, reason, risk factors.
- PENDING → Permit / Deny inline buttons.
- Permit: approve join request + DM user.
- Deny: reject join request + DM user "Account restricted."
- "More details" button: full social profile, ban history, provider attribution, analysis timestamp.

**F6. Security wizard (shipped)**
- `/security` command in private chat: set security preset, instant-ban categories, social profiling toggle, external API toggle, pending score threshold.
- Admin re-check on every wizard callback step.

**F7. Watcher (shipped — partially tested)**
- `on_channel_message`: logs message content to stylometry ingestion pipeline.
- Stylometry vector updated per user per channel on each message.
- Periodic background pass: flags members whose writing pattern matches a banned user above threshold.

**F8. Blockchain registry (shipped)**
- Optional: `CONTRACT_ADDRESS` + `WALLET_PRIVATE_KEY` → BanRegistry.sol on Adiri testnet.
- Chain unavailable (RPC down) → PENDING + ops alert, never silent approve.

---

### UI

**U1.** Verify page shows all five states (loading/blocked/pending/form/success) and never reveals detection reasoning.
**U2.** Privacy policy link on verify form is functional (links to a policy page or external URL). *(Gap: currently `href="#"` — dead link.)*
**U3.** "Account restricted" shown for both block and expired/invalid token.
**U4.** Success state redirects to Telegram (`tg://`) after 1.2 s.

---

### Integration

**I1.** FingerprintJS OSS v4 from CDN; Pro key loaded from precheck response when `FINGERPRINT_PUBLIC_KEY` is set.
**I2.** FastAPI + python-telegram-bot; single process; SQLite for dev, PostgreSQL for production.
**I3.** Hardhat + Solidity BanRegistry on Adiri (Chain ID 2017); optional until chain env vars set.
**I4.** External social API: `SOCIAL_API_URL` + `SOCIAL_API_KEY`; channel-level opt-in; 1.5s timeout.
**I5.** Self-hosted blocklist: `SOCIAL_BLOCKLIST_PATH` points to JSON file.

---

### Testing (current gaps — must close before ship)

| ID | Path | Test needed | Status |
|----|------|------------|--------|
| P0-4 | `POST /api/admin/unban` | HTTP tests: valid key, missing key (403), missing body (422), unknown user (404) | **Open** |
| P0-5 | `verify_ban` taxonomy | Table-driven: all BanCategory values produce correct reason + severity | **Open** |
| P0-6 | `details_*` admin callback | End-to-end: callback fires → fetches social profile → formats card | **Open** |
| P0-7 | `require_admin_key` guard | 503 when `ADMIN_API_KEY` env unset | **Open** |
| P0-8 | `on_channel_message` watcher | Message logged → stylometry ingestion called | **Open** |
| P0-2 | Precheck rate limit | Per-token rate limit test (likely done — confirm) | **Verify** |
| P0-3 | Proxy trust | `TRUSTED_PROXY_IPS` + `X-Forwarded-For` test (likely done — confirm) | **Verify** |
| P1-5 | BanRegistry.sol | `npx hardhat test` in CI / verify gate | **Open** |
| SEC-1 | Security review | `/security-review` on API/auth/admin paths | **Open** |
| SEC-2 | Deep bug hunt | `/deep-bug-hunt` on recent commits | **Open** |

---

## 5. Non-Goals (Out of Scope for Ship)

- External social API vendor integration (deferred; TelegramNativeProvider + blocklist ships first)
- Redis-backed shared rate limiter for multi-worker deploy (P1-9; single-worker Docker ships first)
- reCAPTCHA v3 / IPQualityScore
- Admin web dashboard / multi-tenant SaaS
- Periodic re-verification of existing members
- 24h member audit / cross-channel instant trigger
- Profile photo check via `get_user_profile_photos` (deferred to Phase 1b)

---

## 6. Technical Considerations

**Detection evasion gap (known, documented):**
The fallback fingerprint (UA + screen dims + timezone) is weak — an attacker who clears browser storage and uses a VPN on the same hardware can evade it. FingerprintJS OSS is significantly stronger; Pro is stronger still. Operators who need high confidence should set `FINGERPRINT_PUBLIC_KEY`. This is documented and acceptable for v1.

**Keystroke cold-start:** A new user with no ban history produces no similarity score. The watcher fills the stylometry gap post-join. Detection quality improves with ban record accumulation.

**Social profiling heuristics are soft:** `TelegramNativeProvider` emits soft signals only. It can produce PENDING but not BLOCK on its own. Hard categories (BLOCK) require the blocklist or external API.

**Privacy policy link:** `verify.html` has `href="#"` for the privacy policy. This must be updated to a real URL or `/privacy` endpoint before public ship to satisfy GDPR notice requirements.

**Chain RPC reliability:** Adiri testnet can be flaky. Fail-closed to PENDING (not silent approval) is implemented. Operators should monitor the ops channel for `chain_unavailable` alerts.

**Admin key absent = 503:** `require_admin_key` returns 503 when `ADMIN_API_KEY` is unset — tested by P0-7.

---

## 7. Success Criteria (Ship Bar)

- [ ] `powershell -File scripts\verify.ps1` green (pytest + ruff + Hardhat compile)
- [ ] P0-4 through P0-8 tests written and passing
- [ ] P0-2 and P0-3 confirmed done in IT gap audit
- [ ] Privacy policy link resolved (U2)
- [ ] `security-review` run; no open critical findings
- [ ] `deep-bug-hunt` run; critical issues fixed or documented
- [ ] `docs/DEPLOY.md` matches current compose + env vars

When all items above are checked: emit `SINGULR_PRODUCTION_READY`.
