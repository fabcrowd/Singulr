# PRD: Overnight improve — research, test, harden

**Codename:** `overnight-improve`  
**Branch:** `overnight-improve` (optional)  
**Estimated:** 7 requirements (~1 agent iteration each, loop every 45m)

## Why

`overnight-ops` shipped deploy/observability. This loop **researches gaps**, **expands tests** on high-risk paths (bot, watcher, verify), **hunts critical bugs**, and **lands minimal fixes** — without scope creep into Phase 2 (reCAPTCHA, dashboard, live E2E).

## Goals

1. Documented research dossier + audit trail for overnight work
2. Critical correctness issues from recent commits fixed with tests
3. Bot handler and watcher test coverage beyond happy-path API tests
4. Verify security surface hardened (rate limits, admin API, logging)
5. Full `scripts/verify.ps1` green at completion

## Non-goals

- New product features (payments, dashboard, reCAPTCHA)
- Live Telegram E2E automation
- Large refactors or dependency upgrades
- Unbounded loop without verify gates

## Subagent & skill map (each iteration)

| Phase | Tool | When |
|-------|------|------|
| Explore | `parallel-exploring` / `explore` subagents | Req 1, test-gap discovery |
| Bug hunt | `deep-bug-hunt` skill + subagent | Req 2, every 3rd loop tick |
| Security | `security-review` subagent | Req 5, after code changes |
| Grind | `grinding-until-pass` skill | After any fix, before `complete` |
| Bot UX | `telegram-bot-architect` skill | Bot handler tests (req 3) |
| Autopilot | `python -m orchestrator autopilot *` | Every requirement |

## Success

- `python -m orchestrator autopilot status` → 7/7 done
- `scripts/verify.ps1` exits 0
- Agent outputs `OVERNIGHT_IMPROVE_COMPLETE`
