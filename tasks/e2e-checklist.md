# Singulr E2E Manual Test Checklist

Run against a real Telegram channel with bot configured in `.env`.

## Prerequisites

1. `BOT_TOKEN`, `CHANNEL_ID`, `LOG_CHANNEL_ID`, `PUBLIC_BASE_URL` set
2. Bot is channel admin (ban, invite, restrict)
3. Channel has **approve new members** enabled
4. `uvicorn singulr.main:app` running and reachable at `PUBLIC_BASE_URL`

## Join and verify flow

1. Request to join the channel from a test Telegram account
2. Confirm bot restricts you (cannot post)
3. Confirm bot DMs a verification link within seconds
4. Open link — page loads with Singulr verification sentence
5. Type sentence exactly (paste blocked), accept privacy policy, submit
6. Confirm bot grants channel access within ~30 seconds
7. Confirm welcome/approval message in DM

## Ban evasion (Goal 1)

8. Admin bans the test account from the channel
9. Create a **new** Telegram account (new phone number)
10. Request join again from the **same device/browser**
11. Open verification link — expect block or flag (not silent approve)
12. Confirm log channel receives alert if flagged

## Watcher (Goal 2)

13. Post 10+ casual messages from verified account
14. Ban account, wait for watcher interval (or trigger manually)
15. Confirm stylometry match alert in log channel if style overlaps banned profile

## Chain (optional)

16. After ban, check `orchestrator/runs` or DB for `chain_tx` if wallet configured
17. Look up transaction on https://telscan.io if `CONTRACT_ADDRESS` set

## Pass criteria

- Steps 1–7 pass for clean user
- Steps 8–12 catch same-device rejoin
- Log channel receives structured alerts for flag/ban events
