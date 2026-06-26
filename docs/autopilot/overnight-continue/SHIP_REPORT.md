# Overnight ship report

**Date:** 2026-06-25  
**Verify gate:** `scripts/verify.ps1` (pytest + ruff + hardhat compile)

## Autopilot packs

| Pack | Status | Notes |
|------|--------|-------|
| feature | 12/12 | Member join/verify journey |
| social-profiling | 6/6 | Blocklist, external API, wizard v3 |
| network-trust-registry | 14/14 | Prior session |
| overnight-improve | 7/7 | Prior session |
| production-hardening | 3/3 | CI, Docker, verify page |
| overnight-ops | 6/6 | Rate limit, logging |
| overnight-continue | 3/3 | Docs + this report |

## Test count

180 pytest tests green at last full verify.

## Social profiling shipped

- **Phase 1+2:** Telegram heuristics, join snapshot, token cache, channel policy fields
- **Phase 3+4:** JSON blocklist provider, generic HTTP external API (channel opt-in), `/security` wizard v3 (instant-ban + social toggles)

## Operator next steps

1. Copy `data/social_blocklist.example.json` → production path; set `SOCIAL_BLOCKLIST_PATH`
2. Run `/security` in bot DM to configure instant-ban categories and external API opt-in
3. Point `SOCIAL_API_URL` at your scoring service when ready (POST JSON, 1.5s timeout)

## Loop

30-minute overnight autopilot loop armed for continued pack execution.
