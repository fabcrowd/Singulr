# PRD: Overnight ops — deploy stack, observability, admin API

**Codename:** `overnight-ops`  
**Branch:** `overnight-ops`  
**Estimated:** 6 requirements (~1 session each, or one long Agent loop)

## Why tonight

Production hardening added CI, Docker, and verify smoke tests. The next gap is **running Singulr like a real service**: compose stack, structured logs, abuse protection on verify endpoints, and a minimal admin read API — all testable without live Telegram secrets.

## Goals

1. One-command prod stack: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up`
2. Operators can trace requests (request ID + optional JSON logs)
3. Verify API resists brute-force (per-IP rate limits on precheck/submit)
4. Admins can list bans via API key (read-only, no PII beyond telegram_user_id hashes)
5. `/health` exposes version + uptime for probes
6. `docs/DEPLOY.md` runbook ties it together

## Non-goals

- reCAPTCHA / IPQualityScore
- Web dashboard UI
- Live Telegram E2E tonight
- Chain deploy to mainnet

## Environment (no new secrets required for tests)

| Variable | Purpose |
|----------|---------|
| `ADMIN_API_KEY` | Optional; when set, gates `/api/admin/*` |
| `LOG_JSON` | `true` → JSON log lines |
| `VERIFY_RATE_LIMIT_PER_MINUTE` | Default 30 |

Tests use in-memory SQLite and omit real `BOT_TOKEN`.

## Requirements summary

See `overnight-ops.json` for machine-readable tasks with TDD phases.

## Success

- `python -m orchestrator autopilot status` → 6/6 done
- `scripts/verify.ps1` green
- `docs/DEPLOY.md` exists and matches compose files
