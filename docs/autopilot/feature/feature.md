# PRD: Simplified Member Join & Verify Journey

**Codename:** `feature` (join-verify flow redesign)  
**Status:** Draft for approval  
**Audience:** Product owner, channel admins, implementers  
**Sources:** [docs/plans/my-feature-brainstorm.md](../../plans/my-feature-brainstorm.md); product Q&A (2026-06-25)  
**Related:** Builds on Singulr’s existing verify stack; narrows and reframes the **member-facing** experience while preserving network registry goals described in `network-trust-registry.md`.

---

## 1. Introduction / Overview

Singulr gates Telegram channel joins behind a **one-time verification** flow. Today the system already supports join requests, bot DMs, a web verify page, risk checks, and admin ops — but the product goal of this PRD is to **redesign the member journey** so it feels like a quick, ordinary verification while stronger checks (device fingerprint, behavior, network registry, external APIs) run **invisibly** in the background.

The **true north** identity artifact is a **blockchain-linked profile**: each join enriches the record; ban and ban-evasion events are stored with **dated, categorized reasons** so any Singulr-enabled channel can cross-reference history during **admin review** — without exposing those details to the joiner.

### End-to-end journey (member)

1. User taps **Join** on the channel.
2. Bot sends a **channel-branded DM** with a one-time verify link.
3. User completes a **minimal** web page (typing test + privacy accept; silent fingerprint collection).
4. **Approved** → bot grants channel access and sends a **confirmation DM** with a link to open the channel.
5. **Restricted** → web page shows only **“Account restricted”** (no detailed reason).
6. **Under review** → neutral copy: verification is under review; user will be notified in Telegram DMs when complete.

All outcomes are logged to the **admin Telegram channel**. Only specific outcomes trigger an **instant channel ban** (see §4).

---

## 2. Goals

1. **Frictionless member UX** — Verification feels simple; users are not walked through security concepts or progress “wizards.”
2. **Clear outcomes** — Approve (in + DM), restrict (generic message), or review (DM promise); no leak of ban reasons to joiners.
3. **Fair instant-ban policy** — Instant ban only for **local ban evasion** (high-confidence match to someone already banned *on this channel*) or **admin-configured severe categories** (e.g. bot, impersonation) including high-confidence **external API** hits in those categories.
4. **Cross-channel accountability** — Prior bans on other groups surface in **admin review** with full **date + reason + category** history; they do not alone auto-ban on a new channel.
5. **Compounding blockchain profile** — Each join and each caught evasion attempt updates the shared on-chain record for audit and network cross-reference.
6. **Operator visibility** — Every verify outcome posts to the admin channel; pending cases include **Permit / Deny** actions; restrict and review events include rich context and **More details** (including social profile analysis).
7. **Admin configurability** — Channel admins choose which ban categories trigger instant restrict vs human review via existing security settings (`/security`).

---

## 3. User Stories

### Channel member (joiner)

- As a **new joiner**, I tap Join, get a DM to finish joining **{Channel Name}**, complete a short page, and either enter the channel or see a simple status — without learning about fingerprinting or network bans.
- As an **approved joiner**, I receive a DM confirming I’m in, with a link to open the channel.
- As a **restricted joiner**, I see **“Account restricted”** only — not why.
- As a **joiner under review**, I see that verification is under review and that I’ll get a DM when it’s done.

### Channel admin

- As a **channel admin**, I see **every** verification outcome in my admin Telegram channel (approve, restrict, under review).
- As a **channel admin**, when someone is **under review**, I get **Permit / Deny** buttons and enough context to decide (including prior bans from other groups: date, reason, category).
- As a **channel admin**, I tap **More details** to see an expanded social/profile analysis (Telegram signals + external API enrichment).
- As a **channel admin**, I configure which categories (e.g. impersonation, bot) cause **instant restrict** vs **review** for my channel.
- As a **channel admin**, when I ban someone, I must attach a **reason and category** so other channels’ admins see accurate history during review.

### Network / platform

- As a **network operator**, fingerprints and structured ban events on-chain form a **shared bad-actor repository** across opted-in deployments.
- As a **network operator**, when a joiner has on-chain history elsewhere, the default path is **review** with full ban list — not silent auto-ban — unless local evasion or channel policy says otherwise.

---

## 4. Requirements

### Functional

#### F1. Join request handling

- On `chat_join_request`, bot **restricts** the user (no channel access until verified).
- Bot sends DM: channel-branded copy, e.g. **“Finish joining {Channel Name}: [link]”**.
- Create a **one-time token** tied to `telegram_user_id` + `channel_id`.
- **Token policy:** ~10 minute expiry; **one active link per user** — a new join request **invalidates** the previous token.
- Rate-limited users receive a friendly DM (no crash, no silent failure).

#### F2. Minimal verification web page

- Single-screen, mobile-first layout: feels like a routine check, not a security product.
- Visible steps: short typing test (fixed sentence), privacy acceptance, submit.
- **Silent collection:** device fingerprint, keystroke timing, environment signals — no extra visible steps.
- No copy that mentions blockchain, ban lists, or cross-channel history.

#### F3. Verification decisions (member-visible)

| Internal decision | Member web UI | Bot DM |
|-------------------|---------------|--------|
| Approve | Success state (minimal) | Confirmation + link to channel |
| Block / restrict | **“Account restricted”** only | Optional short DM (no detailed reason) |
| Pending | Under review message | “Verification under review — once completed, you will receive a notification in Telegram DMs.” |

#### F4. Instant ban (channel ban) — strict scope

**Instant ban** (`ban_member` + persist ban) applies only when:

1. **Local ban evasion** — User was previously banned on **this channel**; new `telegram_user_id` reapplies; fingerprint/behavior match exceeds **ban evasion confidence threshold** → malicious regain attempt.
2. **Admin-configured instant-ban categories** — Channel policy marks categories (e.g. `impersonation`, `bot_abuse`) for immediate restrict.
3. **High-confidence external API classification** — API returns a configured instant-ban category (same policy as #2).

**Does not** instant-ban solely because:

- On-chain / network history shows bans from **other** channels (→ **review**).
- Subjective or lower-severity categories flagged (→ **review**).
- Elevated risk without evasion match (→ **review** or flag per policy).

On instant ban: record ban with **category + severity + reason**; contribute to network registry when channel policy allows; emit on-chain event; notify **admin channel**; member sees **Account restricted**.

#### F5. Pending review

- User remains restricted; **not** channel-banned until admin **Deny**.
- Admin channel message includes **Permit** / **Deny** inline actions.
- Admin sees **full cross-channel ban history** when on-chain/network data exists: *“Banned on {date} for {reason}”* per event.
- On **Permit**: grant access + approval DM with channel link.
- On **Deny**: channel ban + generic restricted messaging to user; admin channel audit.

#### F6. Admin channel reporting (all outcomes)

Every verify attempt produces an admin channel post:

| Outcome | Admin channel content |
|---------|------------------------|
| Approve | Compact log (user id, channel, approve) |
| Restrict | Event card + risk summary; audit-only if auto-ban |
| Under review | Actionable card (Permit/Deny) + risk flags |
| All restrict/review | **More details** button → expanded profile |

**More details** includes:

- Telegram-native profile (user id, username, display name, account signals available to bot).
- Internal risk factors (fingerprint match scores, category flags) — **admin only**.
- **Social profile analysis:** Telegram + **external API** enrichment.
- Network ban history list (date, reason, category, source channel when known).

#### F7. Blockchain profile (true north)

- On successful verify, register/update fingerprint on-chain for the deployment.
- On structured ban, write ban record with **category, severity, reason, timestamp, channel id**.
- On **caught local ban evasion**, record evasion attempt on-chain (profile compounding).
- On **read** at join: fetch reputation + ban history for admin review UI; **do not** expose reasons to joiner.
- Prior bans elsewhere → default **review** with full history in admin **More details** / pending card.

#### F8. External API integration

- External APIs supplement Telegram signals for social/profile scoring.
- **Hard category match** (bot, impersonation, etc.) → may trigger instant ban if channel policy allows.
- **Softer signals** → contribute to internal risk score → **review**, not instant ban alone.
- API failures → fail open to local checks only (or channel policy: fail closed to review); never leak API errors to joiner.

#### F9. Ban reason requirement

- Admin-initiated bans and system auto-bans must persist **reason text** and **standard category**.
- Network consumers display ban history to **admins only** during review.
- Reasons are immutable audit fields; overturn/reinstatement flows mark status without erasing history.

### UI

- **Member web:** minimal single screen; generic restricted copy; no security jargon.
- **Bot DMs:** short, channel-branded; no fingerprint/blockchain language.
- **Admin channel:** actionable inline keyboards where needed; **More details** as callback expanding to rich profile view (edit message or threaded detail).

### Integration

- **Telegram Bot API:** join requests, restrict, approve, ban, DMs, inline callbacks.
- **Existing Singulr API:** `/api/verify/precheck`, `/api/verify/submit`, token validation, `apply_verification_decision`.
- **Blockchain:** `BanRegistry` (or successor) for fingerprint register, structured bans, reputation read, evasion annotations.
- **External APIs:** pluggable provider interface for profile/scam/bot checks (specific vendors TBD in technical design).

### Testing

- Member journey E2E: join → DM → submit → approve DM + grant access.
- Restrict path: block decision → “Account restricted” + admin notify + channel ban when instant-ban rules fire.
- Pending path: no ban until Deny; Permit grants access; review DM copy.
- Token: 10m expiry; new join invalidates old token.
- Local evasion: banned fingerprint + new user id → instant ban + on-chain write.
- Cross-channel on-chain ban history → pending + admin sees dated reasons; **no** instant ban from history alone.
- Admin **More details** callback returns Telegram + API enrichment payload.
- Category policy: impersonation instant-ban vs subjective category → review.

---

## 5. Non-Goals (Out of Scope)

- End-user login accounts or passwords.
- Showing ban reasons or network history to joiners.
- Full OSINT dashboard or manual analyst workflow beyond admin Telegram cards.
- Requiring joiners to submit social media links on the verify page (v1 stays invisible; optional links may come later).
- Replacing `/security` wizard — this PRD **consumes** its policy outputs, not re-specifies all knobs.
- Multi-language copy (English v1 unless otherwise specified).

---

## 6. Technical Considerations

- **Reuse** existing modules: `handlers.on_join_request`, `apply_verification_decision`, `matching.check_known_bad`, `channel_policy`, `blockchain.ChainClient`, admin ops callbacks.
- **Align** instant-ban logic with `ban_evasion_auto_deny_threshold` and per-channel `network_auto_reject_categories` / instant-ban category set.
- **Separate** “network history → review” from “local evasion → instant ban” in matching decision tree to avoid regressions.
- **External APIs:** add `singulr/services/social_profile.py` (or similar) with provider interface, timeouts, and redacted logging; cache short-lived results per verify session.
- **More details** callback: new handler pattern `details_{channel_id}_{user_id}` posting expanded admin-only message.
- **Privacy:** fingerprint hashes on-chain only; no PII on-chain; GDPR-style retention documented in ops runbook.
- **Deploy:** `PUBLIC_BASE_URL` must be HTTPS for verify links; bot needs join-request + restrict permissions.

### Decision summary (approved clarifications)

| Topic | Decision |
|-------|----------|
| Primary goal | Redesign/simplify member journey |
| Approve UX | Auto-grant + confirmation DM with channel link |
| Deny UX | “Account restricted” only; admin channel notified |
| Instant ban | Local evasion + configured/API severe categories only |
| Cross-channel bans | Review + full dated reason list for admins |
| Pending UX | Under review copy + DM when complete |
| Web UI | Minimal; background checks invisible |
| Join DM | Channel-branded |
| Token | 10 min; one active link per user |
| Admin feed | All outcomes; Permit/Deny; rich context + More details |
| Social scoring | Telegram + external APIs; D policy (hard category → instant ban; soft → review) |
| Blockchain | Shared repository + cross-reference; profile compounds on each join/evasion |

---

## Next step

After approval, run `/tasks docs/autopilot/feature/feature.md` to generate `feature.json` for autopilot execution.
