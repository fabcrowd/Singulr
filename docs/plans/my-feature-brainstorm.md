# Join verification — brainstorm

## Simple member journey (target)

1. User clicks join on the Telegram channel.
2. Bot sends a DM with a link to the verification webpage.
3. User completes a minimal verification page (feels routine, not “security heavy”).
4. **Approved** → bot grants access automatically + confirmation DM with channel link.
5. **Denied** → user sees only **“Account restricted”** on the site; no detailed reason.

## Admin & network

- All verification outcomes are reported to the **admin Telegram channel**.
- Hard deny (local ban evasion, configured instant-ban categories) → **auto-ban** from the channel.
- Pending / cross-channel history → **review**, not auto-ban from network history alone.
- Ban records must include **date + reason + category**; reviewing admins see full history from other groups.
- **Blockchain profile** is the long-term identity record; enriched on each join and on evasion attempts.

## Social / external

- Telegram-native signals + **external APIs** for profile scoring.
- Admin **More details** button on channel notifications; APIs can trigger instant-ban categories or push to review.

## Link policy

- ~10 minute token TTL.
- One active link per user; new join request invalidates the previous link.
