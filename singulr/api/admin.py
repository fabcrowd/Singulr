"""Read-only admin HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.api.security import require_admin_key
from singulr.db import get_session
from singulr.models import Ban
from singulr.services.reverification import STATUS_REVERIFICATION_REQUIRED, require_reverification

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ReverifyBody(BaseModel):
    """Request body for admin-triggered reverification."""

    telegram_user_id: int


@router.post("/reverify")
async def reverify_user(
    body: ReverifyBody,
    _: None = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Flag a member profile for mandatory reverification."""
    profile = await require_reverification(session, body.telegram_user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="profile_not_found")
    return {
        "ok": True,
        "telegram_user_id": body.telegram_user_id,
        "status": STATUS_REVERIFICATION_REQUIRED,
    }


@router.get("/bans")
async def list_bans(
    _: None = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return local ban records for operator review."""
    rows = (await session.scalars(select(Ban).order_by(Ban.id.desc()))).all()
    return [
        {
            "id": ban.id,
            "telegram_user_id": ban.telegram_user_id,
            "fingerprint_hash": ban.fingerprint_hash,
            "reason": ban.reason,
            "category": ban.category,
            "severity": ban.severity,
            "banned_at": ban.banned_at.isoformat() if ban.banned_at else None,
        }
        for ban in rows
    ]
