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

## Build and start

7. Build images: `docker compose -f docker-compose.yml -f docker-compose.prod.yml build`
8. Start the stack: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`
9. Confirm containers are healthy: `docker compose ps` (app should listen on `0.0.0.0:8000`).

## Health checks

10. Probe liveness: `curl -s http://localhost:8000/health | jq` — expect `status`, `version`, `uptime_seconds`, `db_ok`, and `bot_configured`.
11. Verify request tracing: `curl -si http://localhost:8000/health | grep -i x-request-id` — every response should include `X-Request-ID`.

## Admin API

12. When `ADMIN_API_KEY` is set, list bans: `curl -s -H "X-Admin-Key: $ADMIN_API_KEY" http://localhost:8000/api/admin/bans`
13. Requests without the header return HTTP 401; omitting `ADMIN_API_KEY` in `.env` disables the route (HTTP 503).

## Telegram setup

14. Add the bot to your channel as admin with permission to restrict members and read messages (for The Watcher).
15. Set `CHANNEL_ID` to the numeric channel id and `PUBLIC_BASE_URL` to the HTTPS URL users open for `/verify?token=...`.
16. Send `/start` in a private chat with the bot to confirm polling; join the channel with a test account to exercise verification.

## Operations

17. Tail logs: `docker compose logs -f app` — with `LOG_JSON=true`, lines are JSON access events from `singulr.access`.
18. Rate limits: verify endpoints allow `VERIFY_RATE_LIMIT_PER_MINUTE` requests per client IP per minute; excess returns HTTP 429.
19. Database backups: snapshot the `singulr_pg` Docker volume or use `pg_dump` against the `db` service.
20. Upgrades: pull latest code, rebuild (`docker compose ... build`), and `up -d` with the same compose files.

## Rollback

21. Stop the stack: `docker compose -f docker-compose.yml -f docker-compose.prod.yml down`
22. Restore the previous image tag or git revision, restore DB backup if schema changed, then repeat steps 7–10 before re-enabling Telegram traffic.
