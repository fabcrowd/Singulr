"""FastAPI application and verification page."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from singulr.api.verify import router as verify_router
from singulr.bot.handlers import build_bot_application
from singulr.bot.runtime import set_application
from singulr.config import get_settings
from singulr.db import init_db, engine
from singulr.services.blockchain import ChainClient

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
_bot_app = None
_bot_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and start Telegram bot polling."""
    global _bot_app, _bot_task
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


app = FastAPI(title="Singulr", version="0.1.0", lifespan=lifespan)
app.include_router(verify_router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health() -> dict[str, bool | str]:
    """Health check with component status."""
    settings = get_settings()
    db_ok = True
    try:
        async with engine.connect() as conn:
            await conn.run_sync(lambda _: None)
    except Exception:  # noqa: BLE001
        db_ok = False
    chain = ChainClient()
    return {
        "status": "ok" if db_ok else "degraded",
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
