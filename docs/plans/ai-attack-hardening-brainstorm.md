# AI attack hardening — brainstorm

**Last updated:** 2026-06-26  
**Status:** Design pass — ready for PRD + autopilot pack  
**Audience:** Repo lead (@it), security, channel admins  
**Sources:** Singulr verify stack audit; `IT_GAP_AUDIT.md`; industry notes (tg-bot-detector, Telegram 2026 spam layers)

---

## Problem statement

Singulr gates channel joins with a **typing test + silent fingerprint + risk matching**. That worked against naive scripts; **2026 attackers** use:

- **LLM agents** that read the page, type the verification sentence with human-like delays
- **Headless / CDP browsers** with `navigator.webdriver` patched out
- **Telegram bot farms** with Premium accounts, AI-generated names/photos, and coordinated join waves
- **Replay APIs** that POST crafted `keystrokes` JSON without a real browser
- **Token oracles** on precheck to probe fingerprints before submit

**Today Singulr catches:** obvious webdriver/headless UA (+20 risk **flag only**), paste on verify page, local/network bans, social heuristics, stylometry post-join.

**Today Singulr misses:** synthetic keystroke replay, agentic browsers, farm join clustering, server-side proof that keystrokes came from the real page, escalation from `env_anomaly` flag to hold/deny under strict policy.

---

## Design principles

1. **Invisible to legitimate humans** — no CAPTCHA walls unless channel opts into strict mode.
2. **Defense in depth** — no single signal auto-bans; compose cheap signals → score → pending/block per channel policy.
3. **Server-verifiable** — don't trust client JSON alone; bind sessions cryptographically where possible.
4. **AI-aware, not AI-phobic** — flag automation + farm patterns; let admins Permit/Deny on ambiguous cases.
5. **Fail closed on abuse** — rate limits, token binding, reduced oracles; fail open only where product explicitly chooses conversion over security.
6. **Measurable** — log attack labels (`ai_keystroke_replay`, `join_burst`, `env_anomaly`) for tuning without leaking to joiners.

---

## Threat model (attack inventory)

### A. Verify-page automation (web)

| Attack | How | Current defense | Gap |
|--------|-----|-----------------|-----|
| **A1 — Headless browser** | Puppeteer/Playwright | `webdriver`, `headless_ua` → +20 flag | Patched webdriver; flag not block; trivially spoofable |
| **A2 — LLM typing agent** | Vision + keystroke API | Paste blocked; must type sentence | Synthetic `keystrokes` array in POST; no server nonce |
| **A3 — Keystroke replay** | Copy prior human session | Rhythm compared at match time | Submit API accepts arbitrary JSON; no HMAC/session bind |
| **A4 — Fingerprint rotation** | New visitor_id per attempt | IP velocity, bans | Precheck oracle; unlimited visitor_id tries per token |
| **A5 — Timing bot** | Uniform inter-key delays | Rhythm vector | No "too perfect" / machine rhythm detector |
| **A6 — Direct API abuse** | curl submit without page | Token required | No proof-of-page-work; no CSP-bound challenge |

### B. Telegram-native (join / identity)

| Attack | How | Current defense | Gap |
|--------|-----|-----------------|-----|
| **B1 — Bot farm join wave** | 100+ joins/hour, similar profiles | Social heuristics (username, brand overlap) | No join **velocity/cluster** scoring on `ChatJoinRequest` |
| **B2 — Premium camouflage** | Paid Premium on farm accounts | None | Premium not a trust signal (industry: farms buy Premium) |
| **B3 — AI profile synthesis** | Name + photo look human | `no_username`, empty display name flags | Score-0 bots pass individual heuristics |
| **B4 — Account warming** | Aged accounts with history | Network registry | Read-only pending; doesn't block automation at verify |
| **B5 — Join token farming** | Mass `/start` to burn rate limits | 3 tokens/24h per user | Race on token create; no global join throttle |

### C. Ops / infrastructure

| Attack | How | Current defense | Gap |
|--------|-----|-----------------|-----|
| **C1 — Admin callback tap** | Forward ops message | `_require_ops_admin` | Fixed |
| **C2 — XFF spoof** | Fake `X-Forwarded-For` | Used for rate limit + IP hash | No trusted proxy list |
| **C3 — Multi-worker rate limit bypass** | N replicas × quota | In-memory limiter | No Redis shared limiter |
| **C4 — LLM social API poisoning** | Malicious `SOCIAL_API_URL` response | Parse hardening | External categories not enum-validated |

---

## Signal inventory (what we can add)

### Tier 1 — Low cost, verify page (Phase 1)

| Signal | Detection | Action |
|--------|-----------|--------|
| **Page session nonce** | Server issues nonce at precheck; submit must include HMAC(keystrokes∥nonce) | Reject replay / raw API |
| **Keystroke plausibility** | Min events, hold/flight variance, backspace count, time-to-complete vs length | Flag `synthetic_keystroke`; strict → pending |
| **Env fingerprint bundle** | `plugins.length`, `languages`, `hardwareConcurrency`, `deviceMemory`, WebGL renderer hash | Flag `automation_env`; extend beyond webdriver |
| **Challenge timing** | Elapsed ms from precheck to submit &lt; human floor | Flag `too_fast_verify` |
| **Per-token visitor bind** | First precheck `visitor_id` stored on token row | Later mismatch → pending |
| **Precheck rate limit** | Per-token + per-IP caps | Close oracle |

### Tier 2 — Matching policy (Phase 2)

| Signal | Detection | Action |
|--------|-----------|--------|
| **env_anomaly escalation** | Channel policy: `automation_flag_mode` = flag \| pending \| block | Strict channels pending on webdriver |
| **Synthetic rhythm** | Coefficient of variation too low on flight times | Flag `machine_rhythm` |
| **Join burst** | N join requests same channel in 5 min from similar social cluster | Flag channel; optional auto-hold new joins |
| **AI risk composite** | Weighted score from Tier 1 + social | Compare to `ai_pending_threshold` |

### Tier 3 — Admin / post-join (Phase 3)

| Signal | Detection | Action |
|--------|-----------|--------|
| **Post-join stylometry** | Watcher (existing) | Already planned |
| **Join-date clustering** | Histogram of join timestamps (tg-bot-detector style) | Ops report "suspected farm wave" |
| **Re-verify on anomaly** | High AI score after approve | `require_reverification` (exists) |

### Tier 4 — Optional external (Phase 4, opt-in)

| Signal | Source | Notes |
|--------|--------|-------|
| **Turnstile / hCaptcha** | Cloudflare | Strict preset only; hurts conversion |
| **Bot detection SaaS** | Fingerprint Pro botd, DataDome | Paid; channel opt-in |
| **Telegram account age** | Bot API `user` (limited) | Document limits |

---

## Recommended phased plan

### Phase 1 — Close the API trust gap (2–3 weeks, highest ROI)

**Goal:** Attacker cannot pass verify with curl + guessed token.

1. **Verify session binding**
   - Precheck returns `session_id` + `challenge_secret` (short TTL, single use).
   - Submit requires `challenge_proof` = HMAC-SHA256(secret, canonical keystroke summary).
   - Store first `visitor_id` on token at precheck; mismatch on submit → pending.

2. **Precheck hardening**
   - Per-token rate limit (e.g. 10/min).
   - Trusted proxy config for `X-Forwarded-For`.
   - Reduce oracle: don't return `ip_flagged` to client (ops only).

3. **Keystroke validation**
   - Pydantic bounds: max events, max body size.
   - Server rules: min typing duration, min flight variance, require backspaces/errors for long sentences.

4. **Tests:** replay submit without proof → 400; synthetic flat rhythm → flag; precheck throttle → 429.

**Autopilot reqs:** 1–4 in `ai-attack-hardening.json`.

---

### Phase 2 — Automation scoring & policy (1–2 weeks)

**Goal:** Channel admins choose how hard to treat automation signals.

1. **`ChannelSecuritySettings` extensions**
   - `automation_flag_mode`: `flag` \| `pending` \| `block`
   - `ai_pending_score_threshold` (default 50)
   - `min_verify_duration_ms` (default 3000)

2. **Extended `env_flags`**
   - Client collects: `plugins_count`, `languages_count`, `webgl_renderer`, `outer_dims_zero`.
   - Server: `_env_anomaly_detected` expanded; weight in composite AI score.

3. **`/security` wizard v4** — automation strictness step (reuse wizard patterns).

4. **Matching integration** — composite `ai_automation_score`; pending when ≥ threshold under strict preset.

**Autopilot reqs:** 5–7.

---

### Phase 3 — Join-side farm detection (1–2 weeks)

**Goal:** Catch coordinated join waves before verify completes.

1. **Join velocity tracker** — Redis or DB sliding window per `channel_id`.
2. **`on_join_request` enrichment** — snapshot join burst score into token row / social context.
3. **Ops alert** — "Join burst detected" message when velocity &gt; configured cap.
4. **Optional:** delay DM link delivery by random 2–8s for burst joiners (anti-script).

**Autopilot reqs:** 8–10.

---

### Phase 4 — Strict mode extras (optional)

1. Cloudflare Turnstile on verify page (channel flag).
2. External bot-detection provider hook (parallel to `ExternalApiProvider`).
3. Post-approve reverification trigger when watcher + AI score disagree.

**Autopilot reqs:** 11–12 (nonGoals if vendor keys unavailable).

---

## Non-goals (this pack)

- Replacing Telegram join flow with off-platform KYC
- ML model training pipeline in-repo (heuristics + thresholds first)
- Blocking all AI assistants globally (would harm legitimate users)
- Live CAPTCHA on every join for all channels (strict opt-in only)

---

## Success metrics

| Metric | Target |
|--------|--------|
| Replay submit without session proof | **0%** success in tests |
| Precheck oracle brute-force | Rate-limited; no unbounded `visitor_id` tries |
| `verify.ps1` | Green after each phase |
| Regression | Existing approve path unchanged for clean human fixture |
| Ops | New risk factors documented in DEPLOY.md |

---

## Open decisions (Lead defaults)

| # | Question | Proposed default |
|---|----------|------------------|
| 1 | Block vs pending on webdriver in balanced preset? | **Pending** (not block) |
| 2 | Store challenge secret on token row vs Redis? | **Token row** (SQLite/Postgres already) |
| 3 | Turnstile in v1? | **Phase 4** only |
| 4 | Emit AI score to joiner? | **Never** — ops/admin only |

---

## Next artifacts

1. PRD: `docs/autopilot/ai-attack-hardening/ai-attack-hardening.md`
2. Task pack: `docs/autopilot/ai-attack-hardening/ai-attack-hardening.json`
3. Cross-link from `IT_GAP_AUDIT.md` Phase AI
4. Dev agent: `python -m orchestrator autopilot use docs/autopilot/ai-attack-hardening/ai-attack-hardening.json`
