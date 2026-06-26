# Singulr deployment runbook

Production deployment for the FastAPI + Telegram bot stack using Docker Compose.

## Prerequisites

1. Install Docker Engine and Docker Compose v2 on the host.
2. Clone the Singulr repository and `cd` into the project root.
3. Copy `.env.example` to `.env` and fill in required values (see step 6).
4. Ensure ports `8000` (API) and `5432` (Postgres, optional external access) are available.
5. Rotate `BOT_TOKEN` in BotFather before pointing at a production channel.

## Environment

6. Set core variables in `.env`: `BOT_TOKEN`, `CHANNEL_ID`, `PUBLIC_BASE_URL`, and `DATABASE_URL` (Compose prod sets this automatically for the app service). Optional: `ADMIN_API_KEY`, `LOG_JSON=true`, `VERIFY_RATE_LIMIT_PER_MINUTE=30`, chain fields for Adiri testnet.

### AI attack hardening (verify session)

7. **Verify session binding** (shipped): the verify page must complete precheck before submit. Precheck returns a one-time `challenge_secret`; the browser sends `challenge_proof` (HMAC-SHA256) on submit. Direct API replay without precheck returns HTTP 400 `challenge_invalid`. No extra env vars — secrets are per-token in the database (`verify_challenge_secret` column).

8. **Rate limits:** `VERIFY_RATE_LIMIT_PER_MINUTE` (default `30`) applies per client IP to both `/api/verify/precheck` and `/api/verify/submit`. Excess requests return HTTP 429.

9. **Reverse proxy (planned):** when deployed behind a trusted load balancer, set `TRUSTED_PROXY_IPS` (comma-separated) so `X-Forwarded-For` is honored only from known hops. Until req 4 ships, rate limits and IP hashing use the direct connection IP.

### Security presets (`/security` wizard)

10. **open** — highest auto-approve thresholds; network registry off by default.  
11. **balanced** — default production preset; moderate evasion sensitivity.  
12. **strict** — lower ban-evasion and similarity thresholds (more admin review). Upcoming automation controls (reqs 5–6) will escalate `webdriver` / synthetic keystroke signals to pending under strict channels via `automation_flag_mode`.

## Build and start

13. Build images: `docker compose -f docker-compose.yml -f docker-compose.prod.yml build`
14. Start the stack: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`
15. Confirm containers are healthy: `docker compose ps` (app should listen on `0.0.0.0:8000`).

## Health checks

16. Probe liveness: `curl -s http://localhost:8000/health | jq` — expect `status`, `version`, `uptime_seconds`, `db_ok`, and `bot_configured`.
17. Verify request tracing: `curl -si http://localhost:8000/health | grep -i x-request-id` — every response should include `X-Request-ID`.

## Admin API

18. When `ADMIN_API_KEY` is set, list bans: `curl -s -H "X-Admin-Key: $ADMIN_API_KEY" http://localhost:8000/api/admin/bans`
19. Requests without the header return HTTP 401; omitting `ADMIN_API_KEY` in `.env` disables the route (HTTP 503).

## Telegram setup

20. Add the bot to your channel as admin with permission to restrict members and read messages (for The Watcher).
21. Set `CHANNEL_ID` to the numeric channel id and `PUBLIC_BASE_URL` to the HTTPS URL users open for `/verify?token=...`.
22. Send `/start` in a private chat with the bot to confirm polling; join the channel with a test account to exercise verification.

## Social profiling (optional)

23. Copy `data/social_blocklist.example.json` to a persistent path on the host; set `SOCIAL_BLOCKLIST_PATH` in `.env` (mounted into the app container if using Compose).
24. Optionally set `SOCIAL_API_URL` and `SOCIAL_API_KEY` for an external scoring HTTP API. Channels must opt in via the bot **`/security`** wizard (v3) — toggle **External API** on question 7.
25. Channel admins run `/security` in a private chat to set instant-ban categories (question 6) and social profiling toggles. Wizard version 3 persists `instant_ban_categories`, `social_profiling_enabled`, and `social_external_api_enabled`.

## Operations

26. Tail logs: `docker compose logs -f app` — with `LOG_JSON=true`, lines are JSON access events from `singulr.access`.
27. Rate limits: verify endpoints allow `VERIFY_RATE_LIMIT_PER_MINUTE` requests per client IP per minute; excess returns HTTP 429.
28. Database backups: snapshot the `singulr_pg` Docker volume or use `pg_dump` against the `db` service.
29. Upgrades: pull latest code, rebuild (`docker compose ... build`), and `up -d` with the same compose files.

## Rollback

30. Stop the stack: `docker compose -f docker-compose.yml -f docker-compose.prod.yml down`
31. Restore the previous image tag or git revision, restore DB backup if schema changed, then repeat build/start steps before re-enabling Telegram traffic.
