# PRD: Network Trust Registry & Behavioral Fingerprinting

**Codename:** `network-trust-registry`  
**Status:** Draft for review  
**Replaces:** Initial prompt (“add user login feature”) — Singulr does **not** need end-user login; identity is established at first verification and reinforced over time.

## Introduction / Overview

Singulr protects Telegram communities from **ban evasion**: users who were removed for abuse rejoining with a new phone number or account. The bot’s core value is to build a **durable behavioral and device fingerprint** tied to a Telegram user ID at first verification, persist signals locally, and anchor key state on a **shared on-chain repository** that any channel running Singulr can query.

When someone applies to join a channel, the system:

1. Collects verification signals (device fingerprint, keystroke cadence, writing style over time).
2. Checks **local** bans and fingerprint matches.
3. Queries the **network registry** for category-weighted ban history and reputation score.
4. Applies **tiered decisions** — auto-approve, **auto-deny** for high-confidence ban evasion, or **pending admin review** only for elevated-but-uncertain risk.
5. Routes **pending** cases to a **private admin Telegram group** for approve/deny; **auto-deny** cases still notify ops for audit and DM the user with a denial reason.

This PRD specifies the **complete product vision** (cross-channel scoring, standardized ban categories, reinstatement). Implementation is **staged** so channels can ship value incrementally without re-architecting.

## Goals

1. **Prevent ban evasion** — Detect when a join attempt likely belongs to a previously banned person, even under a new Telegram account.
2. **Establish a base profile at first verify** — Link Telegram user ID to fingerprint hash, keystroke profile, and evolving stylometry; register fingerprint on-chain.
3. **Shared network repository** — Any Singulr deployment can read (and eligible channels write) ban records and reputation scores keyed by fingerprint / profile identity.
4. **Graduated risk handling** — High-confidence ban-evasion matches **auto-deny**; only uncertain elevated risk enters admin review.
5. **Standardized, severity-tiered ban categories** — Consistent labels (spam, solicitation, scam, etc.) drive auto-reject rules, score weighting, and decay.
6. **Fair reinstatement** — Hybrid unban: local mistakes reversible quickly; serious categories require appeal; some offenses decay over time.
7. **Operator clarity** — Admins are notified of auto-denied ban-evasion attempts for audit; uncertain cases get Permit/Deny controls in the ops channel.
8. **Self-service security tuning** — Channel admins configure protection levels through a **private Q&A with the bot** (Facebook-style security checkup), revisitable at any time.

## User Stories

### Channel member (joiner)

- As a **new joiner**, I complete the verification “test” once so Singulr can create my profile and check I am not a known bad actor, without creating a password or “logging in.”
- As a **returning member** flagged for reverification, I receive a bot DM with a one-time link to complete checks again if an admin requests it.
- As a **joiner auto-denied for ban evasion**, I receive a DM with a denial reason; I do not enter the channel.
- As a **joiner under review** (elevated but not high-confidence match), I remain in **pending** until admins decide; I then receive a DM with either a denial reason or a link to join.

### Channel admin

- As a **channel admin**, I want **high-confidence** ban-evasion attempts (previously banned under another user ID or number) to be **auto-denied**, with an ops notification for audit.
- As a **channel admin**, I want **uncertain** elevated-risk join attempts to land in **pending** and notify my **private admin group**, so my team can permit or deny with context.
- As a **channel admin**, I want to ban someone with a **standard category and severity**, and choose whether that ban is **shared to the network** (if my channel is opted in / trusted).
- As a **channel admin**, I want to **unban locally** when we made a mistake, and understand how that affects network reputation.
- As a **channel admin**, I want to configure **thresholds** for when network score causes auto-reject vs flag vs allow.
- As a **channel admin**, I want to run a **private Q&A with the bot** (like a security checkup) to choose my channel’s protection level — strictness of ban-evasion auto-deny, network registry use, category rules, and ops notifications — and **change those settings anytime** without editing config files.
- As a **channel admin**, I want the bot to **recommend** settings based on my answers (with plain-language tradeoffs) while still letting me pick what fits our community.

### Channel admin — security setup (Q&A)

- As a **new channel admin**, I complete a one-time **security onboarding** in a private DM with the bot when Singulr is first connected to my channel.
- As a **returning admin**, I send `/security` (or tap **Security settings** in the bot menu) to re-run the Q&A and update preferences at any time.
- As an **admin mid-setup**, I can pause and resume later; the bot remembers my last answered question.

### Network operator (platform)

- As a **network operator**, I want only **opt-in or trusted** channels’ bans to affect global score, while still logging all shared events for audit.
- As a **network operator**, I want **category + severity** on-chain so lookups at join time are deterministic and fast.
- As a **network operator**, I want an **appeal / reinstatement** path that updates on-chain status without erasing audit history.

### Abuse victim / community

- As a **community**, we want repeat spammers and scammers to be blocked across channels that use Singulr, not just the one channel that first banned them.

## Requirements

### Functional

#### F1. Initial verification profile (no login)

- First successful verification creates a **Profile** linked to `telegram_user_id` with:
  - Device `fingerprint_hash` (from client signals + server hashing).
  - `keystroke_profile` from verification typing test.
  - Optional initial stylometry (expanded by channel message logging / Watcher).
- Profile status: `approved`, `pending`, `rejected`, `reverification_required`.
- On first approve, write **fingerprint registration** to on-chain registry (hash only, no PII).

#### F2. Behavioral fingerprint accumulation

- **Keystroke cadence** — captured at verify; similarity checked against banned profiles.
- **Stylometry** — feature vectors merged from channel messages over time (Watcher job).
- **Environment signals** — automation/headless flags contribute to risk score, not necessarily auto-ban alone.
- **IP velocity** — same IP verifying multiple distinct users within 24h elevates risk.
- System logs behavioral data for matching; raw message content retention policy configurable (see Technical Considerations).

#### F3. Join-time decision engine (hybrid local + network)

On every join / verify submission, run in order:

1. **Local exact match** — banned `telegram_user_id` or `fingerprint_hash` → `block`.
2. **Ban-evasion similarity (high confidence)** — new `telegram_user_id` with keystroke and/or stylometry similarity to a **previously banned** profile (this channel or network) at or above `ban_evasion_auto_deny_threshold` → `block` (auto-deny). Includes matches across another phone number / account linked to the same behavioral fingerprint.
3. **Ban-evasion similarity (medium confidence)** — similarity above `local_similarity_flag_threshold` but below auto-deny threshold → `pending` (admin review).
4. **On-chain registry query** — fetch ban records and aggregate **network score** for fingerprint-linked identity.
5. **Network rules** — if any **active** ban exists in a **permanent** or configured auto-reject category → `block`.
6. **Score bands** — combine remaining local risk factors + network score:
   - Below channel “review threshold” → `approve`.
   - Between review and reject thresholds → `pending` (admin review).
   - Above reject threshold → `block`.

**Product rule (confirmed):** If someone was **previously banned** (local or network registry) under **another Telegram user ID or phone number**, and verification produces a **high-probability behavioral/device match**, the outcome is **`block` (auto-deny)** — not pending. The user receives a DM with denial reason; ops group receives an **audit notification** (informational). **Pending** is reserved for elevated risk that does **not** meet the high-confidence ban-evasion bar.

#### F4. Admin review workflow (Telegram)

- Configure `ADMIN_OPS_CHAT_ID` (private group) per deployment.
- On **`pending`**, bot posts structured message: user ID, risk factors, matched ban ID, network score summary, category highlights. Inline actions: **Permit** / **Deny** (with reason picker aligned to categories).
- On **`block` (auto-deny ban evasion)**, bot posts an **audit-only** message (match scores, linked banned identity, category) — no Permit action; denial already applied. Ops may open an appeal flow separately (F9).
- On **Permit** — grant channel access; DM user join link or confirmation.
- On **Deny** — keep blocked; DM user with **denial reason** (category-aware template).
- On **auto-deny** — DM user with denial reason immediately (ban evasion template).
- Audit log all decisions locally and (if shared) to network event log.

#### F5. Standardized ban categories with severity tiers

Every ban (local and network-shared) MUST include:

| Category | Description | Typical default tier |
|----------|-------------|----------------------|
| `spam` | Unsolicited bulk / repetitive messages | low–medium |
| `solicitation` | Unwanted sales, DM scraping, promo | medium |
| `scam_fraud` | Financial scams, phishing | high / **permanent** |
| `harassment` | Targeted abuse, threats | medium–high |
| `bot_abuse` | Automated or coordinated bot behavior | medium |
| `impersonation` | Pretending to be another person/org | high |
| `nsfw` | Policy-violating adult content | medium |
| `raid_coordination` | Organized group raids | high |
| `other` | Operator-defined; requires note | low |

**Severity tiers:** `low`, `medium`, `high`, `permanent`

- Tier affects **score weight**, **auto-reject eligibility**, and **decay / appeal** rules.
- Channels MUST select category + tier when banning via bot callback or admin API.

#### F6. Network registry — read on every join

- `ChainClient` (or successor) exposes:
  - `is_banned(fingerprint_hash)` — legacy boolean check.
  - `get_reputation(fingerprint_hash)` → `{ score, active_bans[], overturned_bans[] }`.
- Lookup runs on **every** channel join verification path (precheck and/or submit).
- Latency budget: &lt; 2s p95 including chain RPC (fallback: defer to local-only with logged warning if chain unavailable — channel policy chooses fail-open vs fail-closed).

#### F7. Network registry — write model (opt-in / trusted)

- **All channels** may log bans locally always.
- **Network score contribution** only from:
  - Channels with `share_bans_to_network=true`, AND
  - Channels on **trusted list** (operator-curated) OR meeting trust criteria (age, volume, false-positive rate).
- Write payload: `fingerprint_hash`, `category`, `severity`, `channel_id`, `timestamp`, `reporter_id` (hashed), optional `stylometry_hash`.
- Non-trusted opt-in channels: logged but **weight = 0** until promoted.

#### F8. Channel security settings (Q&A wizard + storage)

Channel policy is stored **per `channel_id`** (DB model `ChannelSecuritySettings` or equivalent), not only in env vars. Env provides **defaults** for new channels; the bot wizard is the primary admin interface.

##### F8.1 Security setup wizard (private admin DM)

- **Who:** Telegram users with **administrator** rights on the target channel (verified via Bot API `getChatMember`).
- **Where:** **Private 1:1 chat** with the bot — never in the public channel.
- **Entry points:**
  - First connect / `/start` as channel admin → offer “Set up security for [channel]”
  - `/security` or `/security <channel_id>` → start or resume wizard
  - Inline **Security settings** button on ops/audit messages (deep-link to DM)
- **Flow (PRD-style Q&A):**
  - One question per message; **lettered options (A, B, C, D)** + short **recommendation** (“I’d suggest B because…”).
  - Progress indicator (“Question 3 of ~10”).
  - After last question → **summary card** of chosen policy → **Confirm** / **Go back** / **Switch to preset**.
  - On confirm → persist settings; post confirmation to admin DM and optionally pin a one-line summary.
- **Reconfiguration:** Admins may re-run the wizard **at any time**; changes apply immediately to new join/verify attempts (in-flight pending cases keep prior policy unless channel opts to re-evaluate).
- **Presets** (starting points, then refined by Q&A):
  - **Open** — minimal network checks; more human review; looser similarity thresholds.
  - **Balanced** (default recommendation) — auto-deny on high-confidence ban evasion; pending for medium; network read enabled.
  - **Strict** — aggressive auto-deny/auto-reject; lower review band; network write opt-in suggested.
  - **Custom** — walk through every knob.

##### F8.2 Example wizard topics (maps to stored fields)

| Question theme | Example options | Maps to |
|----------------|-----------------|---------|
| Overall strictness | Open / Balanced / Strict | Preset bundle |
| Ban evasion on new account | Auto-deny high matches only / Also flag medium / Review almost everything | `ban_evasion_auto_deny_threshold`, `local_similarity_flag_threshold` |
| Network registry | Off / Read only / Read + share our bans | `network_registry_mode`, `share_bans_to_network` |
| Network auto-reject | Which categories (multi-select chips) | `network_auto_reject_categories[]` |
| Uncertain risk | More pending reviews / More auto-rejects | `network_score_review_min`, `network_score_reject_min` |
| Chain unavailable | Fail open (local only) / Fail closed (pending) | `fail_closed_on_chain_error` |
| Ops notifications | Audit-only on auto-deny / Also ping on every pending | `ops_notify_level` |
| Admin ops group | Link this group / Skip for now | `admin_ops_chat_id` |

##### F8.3 Stored settings (per channel)

- `network_score_review_min` — enter pending review.
- `network_score_reject_min` — auto-reject.
- `local_similarity_flag_threshold` — keystroke/stylometry; above → eligible for **pending** review.
- `ban_evasion_auto_deny_threshold` — at or above → **auto-deny** when matched to a banned profile on another user ID / number.
- `fail_closed_on_chain_error` — bool.
- `network_registry_mode` — `off` | `read` | `read_write`.
- `share_bans_to_network` — bool (requires `read_write` and channel trust rules per F7).
- `network_auto_reject_categories[]` — subset of F5 categories.
- `security_preset` — `open` | `balanced` | `strict` | `custom` (audit label).
- `wizard_completed_at`, `wizard_version` — for migrations when new questions are added.

##### F8.4 Wizard versioning

- When new questions are added to the wizard, bump `wizard_version`; prompt admins on next `/security` to answer **delta questions** only (not full re-onboarding unless they choose “Review all”).

#### F9. Reinstatement / unban (hybrid)

| Action | Local DB | Network registry | Score |
|--------|----------|------------------|-------|
| **Local unban** (admin mistake) | Remove or mark overturned | If this channel contributed the ban, emit `BanOverturned` event | Recalculate; reduce weight |
| **Time decay** | N/A | `low`/`medium` categories decay after configurable months | Automatic score reduction |
| **Network appeal** | Appeal record | Trusted reviewer marks `overturned` on-chain | Restores eligibility; history retained |
| **Permanent categories** | Local unban only | `scam_fraud`, `raid_coordination` (configurable) require manual appeal | No automatic decay |

- On-chain status values: `active`, `overturned`, `expired` (decayed).
- Appeals do **not** delete historical records.

#### F10. Admin-triggered reverification

- Admins can flag `reverification_required` on a user (bot command or admin API).
- User’s next join or periodic check forces new verification flow (one-time bot link).
- No separate web login.

#### F11. Decision engine uses channel settings

- `check_known_bad` and verify handlers MUST load **effective policy** from `ChannelSecuritySettings` for the join’s `channel_id`, falling back to env defaults if wizard not completed.
- Log which `security_preset` / policy version produced each decision (audit trail).

### UI (Telegram + verify web)

- **Security wizard (private DM)** — conversational Q&A with inline keyboards (A/B/C/D), Back, Confirm summary; `/security` to reopen anytime; resume interrupted sessions.
- **Bot menu** — “Security settings”, “View current policy” (read-only summary in DM).
- **Verify web page** — unchanged core UX: typing test + device signals; show pending state copy when applicable.
- **Admin ops group messages** — pending: Permit/Deny; auto-deny: audit-only with match detail and linked ban reference.
- **User DMs** — approved: join link; denied / auto-denied: reason string tied to category; pending: “under review” with no join link.
- **Ban callback** — extend inline ban flow to require category + severity selection (multi-step or sensible defaults).

### Integration

- **Telegram Bot API** — join requests, restrict, grant, DM, callback queries, scheduled Watcher job.
- **On-chain BanRegistry contract** — extend from boolean `isBanned` to structured records (category, severity, status, channel source).
- **Fingerprint.com** (optional) — visitor ID + server-side sealing (existing `fingerprint_public_key` config).
- **Existing services** — `matching.check_known_bad`, `watcher`, `stylometry`, `tokens`, `bans` — extended, not replaced.

### Testing

- Unit tests for score aggregation, category weights, decay math, threshold decisions.
- Integration tests for verify API paths: approve, flag/pending, block, chain mock.
- Bot handler tests: pending → admin callback → DM outcomes; security wizard state machine (question flow, confirm, persist, re-run).
- Bot handler tests: non-admin cannot run wizard for a channel they don’t administer.
- Contract tests (Hardhat) for register, ban, overturn, reputation read.
- Regression tests for high-confidence ban-evasion match → **auto-deny** (`block`), ops audit message, user DM.
- Regression tests for medium-confidence similarity → **pending**, admin callback flow.
- Security tests: admin ops actions authorized; internal ban API authenticated.

## Non-Goals (Out of Scope)

- End-user **login**, passwords, email accounts, or Telegram Login Widget sessions.
- Public web dashboard for users (admin dashboard remains future work).
- **Web-based** admin settings UI — channel policy is configured **via bot Q&A in private DM** for v1; no separate settings portal required.
- reCAPTCHA / IPQualityScore (Phase 2 elsewhere).
- Cross-platform identity outside Telegram + verification fingerprint.
- Fully decentralized governance / DAO for trust list (operator-curated is sufficient for v1).
- Storing raw chat message content on-chain or in the public registry.
- Legal compliance program (GDPR export/delete) — noted in Technical Considerations but not implemented here.

## Technical Considerations

### Current codebase alignment

Singulr already implements pieces of this vision:

- `singulr/services/matching.py` — tiered `Decision` (approve / flag / block), keystroke & stylometry similarity, chain boolean check.
- `singulr/api/verify.py` — precheck/submit, profile creation, `_notify_bot` → `apply_verification_decision`.
- `singulr/bot/handlers.py` — join restrict, admin approve/ban callbacks, Watcher job; **extend** with conversation/state machine for security wizard.
- `singulr/services/blockchain.py` — `ChainClient` stub; `record_ban` not fully wired; contract schema needs extension.
- `singulr/models` — `Profile`, `Ban`, `StylometryProfile`, `MessageLog`; add **`ChannelSecuritySettings`**.

This PRD **extends** these modules rather than introducing a parallel auth stack.

### Staged implementation (recommended)

| Phase | Deliverable | User-visible outcome |
|-------|-------------|----------------------|
| **1** | Profile anchor + ban-evasion auto-deny at high confidence; pending for medium confidence; category fields on local `Ban`; ops group flows; **basic `/security` wizard** (preset + 4–5 core questions) | Admins tune strictness in private DM without touching env |
| **2** | On-chain fingerprint register + structured ban read at verify; category auto-reject; wizard maps network registry mode | Network-aware policy chosen via Q&A |
| **3** | Weighted network score, opt-in/trusted write path, channel thresholds | Cross-channel reputation affects join decisions |
| **4** | Decay, appeals, overturn transactions, reinstatement DM flows | False positives recover; serious bans appealable |

Autopilot task generation should **order requirements** 1 → 4 to avoid blocking on contract work.

### On-chain data model (target)

```text
FingerprintRecord:
  fingerprint_hash: bytes32
  registered_at: timestamp
  registrant_channel: uint64

BanRecord:
  fingerprint_hash: bytes32
  category: uint8 (enum)
  severity: uint8 (enum)
  status: active | overturned | expired
  channel_id: uint64
  banned_at: timestamp
```

Public reads return active bans + computed score; writes restricted to authorized registrar role.

### Privacy & retention

- On-chain: **hashes and enums only**.
- Off-chain: keystroke/stylometry vectors, message feature summaries — encrypt at rest in production; define retention window for `MessageLog`.
- User DMs must not leak other channels’ names unless channel opts into transparency.

### Failure modes

- Chain RPC down: configurable fail-open (approve with local checks only) vs fail-closed (pending).
- False positive similarity: medium-confidence → admin Deny via pending; high-confidence auto-deny → appeal flow (F9) + local/network overturn.
- Griefing by rogue channel: trusted list + zero weight until promoted.

### Success criteria

1. Joiner previously banned under another Telegram ID / number with **high-confidence** fingerprint match → **auto-deny**, ops audit message, user DM with reason.
2. Joiner with **medium-confidence** similarity only → **pending**, ops Permit/Deny flow.
3. Fingerprint with active `scam_fraud` / permanent network ban → auto-reject at verify on any channel.
4. Local unban + overturn event → user can verify successfully (score below threshold).
5. Opt-in untrusted channel ban → logged but does not alone push score above reject threshold.
6. Full `scripts/verify.ps1` green after each phase merge.
7. Channel admin completes security Q&A in private DM → settings persisted → next verify uses new thresholds; re-run `/security` updates policy without redeploy.

---

**Next step:** Review and approve this PRD, then run:

```text
/tasks docs/autopilot/network-trust-registry/network-trust-registry.md
```

to generate a code-aware autopilot task JSON.
