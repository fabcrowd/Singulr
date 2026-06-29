"""FastAPI application and verification page."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from singulr.api.admin import router as admin_router
from singulr.api.verify import router as verify_router
from singulr.bot.handlers import build_bot_application
from singulr.bot.runtime import set_application
from singulr.config import get_settings
from singulr.db import init_db, engine
from singulr.middleware.logging import RequestLoggingMiddleware, configure_access_logging
from singulr.services.blockchain import ChainClient

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
_bot_app = None
_bot_task: asyncio.Task | None = None
_app_started_at: float | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and start Telegram bot polling."""
    global _bot_app, _bot_task, _app_started_at
    _app_started_at = time.monotonic()
    await init_db()
    settings = get_settings()
    if settings.bot_configured:
        _bot_app = build_bot_application()
        set_application(_bot_app)
        await _bot_app.initialize()
        await _bot_app.start()
        if _bot_app.updater:
            await _bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started")
    yield
    if _bot_app:
        if _bot_app.updater:
            await _bot_app.updater.stop()
        await _bot_app.stop()
        await _bot_app.shutdown()
    if _bot_task and not _bot_task.done():
        _bot_task.cancel()


_settings = get_settings()
configure_access_logging(log_json=_settings.log_json)

app = FastAPI(title="Singulr", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware, log_json=_settings.log_json)
app.include_router(verify_router)
app.include_router(admin_router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health() -> dict[str, bool | str | float]:
    """Health check with component status."""
    settings = get_settings()
    db_ok = True
    try:
        async with engine.connect() as conn:
            await conn.run_sync(lambda _: None)
    except Exception:  # noqa: BLE001
        db_ok = False
    chain = ChainClient()
    uptime_seconds = round(time.monotonic() - _app_started_at, 2) if _app_started_at else 0.0
    return {
        "status": "ok" if db_ok else "degraded",
        "version": app.version,
        "uptime_seconds": uptime_seconds,
        "db_ok": db_ok,
        "bot_configured": settings.bot_configured,
        "chain_enabled": chain.enabled,
    }


@app.get("/verify", response_model=None)
async def verify_page(token: str = "") -> FileResponse | HTMLResponse:
    """Serve verification webpage."""
    index = STATIC_DIR / "verify.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<h1>verify.html missing</h1>", status_code=500)


@app.get("/privacy", response_model=None)
async def privacy_page() -> FileResponse | HTMLResponse:
    """Serve privacy policy page."""
    page = STATIC_DIR / "privacy.html"
    if page.exists():
        return FileResponse(page)
    return HTMLResponse(
        """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Privacy Policy — Singulr</title>
<style>body{font-family:sans-serif;max-width:700px;margin:3rem auto;padding:0 1rem;line-height:1.6}h1{font-size:1.4rem}</style>
</head>
<body>
<h1>Privacy Policy</h1>
<p>Singulr collects the following data during the join verification process:</p>
<ul>
  <li><strong>Device fingerprint</strong> — a hash derived from browser characteristics. The raw value is never stored; only the hash is kept.</li>
  <li><strong>Keystroke timing</strong> — key-down/key-up intervals while you type the verification sentence. Used to detect returning banned users by typing pattern.</li>
  <li><strong>IP address hash</strong> — a one-way hash of your IP address. The raw IP is never stored.</li>
  <li><strong>Telegram user ID and display name</strong> — provided by Telegram when you request to join.</li>
</ul>
<p>This data is used solely to enforce community safety rules and prevent ban evasion. It is not sold to third parties. Raw messages are never stored; only statistical writing-style summaries are kept for returning-user detection.</p>
<p>To request deletion of your data, contact the channel administrator.</p>
</body>
</html>""",
        media_type="text/html",
    )
