"""Read-only admin HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.api.security import require_admin_key
from singulr.db import get_session
from singulr.models import AppealRecord, Ban
from singulr.services.blockchain import ChainClient
from singulr.services.reinstatement import (
    create_appeal,
    local_unban,
    reinstatement_success_message,
)
from singulr.services.reverification import STATUS_REVERIFICATION_REQUIRED, require_reverification

router = APIRouter(prefix="/api/admin", tags=["admin"])
_chain = ChainClient()


class ReverifyBody(BaseModel):
    """Request body for admin-triggered reverification."""

    telegram_user_id: int


class UnbanBody(BaseModel):
    """Request body for local unban / overturn."""

    telegram_user_id: int | None = None
    ban_id: int | None = None


class AppealBody(BaseModel):
    """Request body for creating a reinstatement appeal."""

    telegram_user_id: int
    reason: str = ""
    ban_id: int | None = None
    fingerprint_hash: str | None = None


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


@router.post("/unban")
async def unban_user(
    body: UnbanBody,
    _: None = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Locally overturn a ban and emit chain overturn when configured."""
    if body.ban_id is None and body.telegram_user_id is None:
        raise HTTPException(status_code=400, detail="ban_id_or_telegram_user_id_required")
    ban = await local_unban(
        session,
        _chain,
        ban_id=body.ban_id,
        telegram_user_id=body.telegram_user_id,
    )
    if ban is None:
        raise HTTPException(status_code=404, detail="active_ban_not_found")
    return {
        "ok": True,
        "ban_id": ban.id,
        "status": ban.status,
        "message": reinstatement_success_message(),
    }


@router.post("/appeals")
async def submit_appeal(
    body: AppealBody,
    _: None = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a pending reinstatement appeal record."""
    appeal = await create_appeal(
        session,
        telegram_user_id=body.telegram_user_id,
        reason=body.reason,
        ban_id=body.ban_id,
        fingerprint_hash=body.fingerprint_hash,
    )
    return {
        "ok": True,
        "appeal_id": appeal.id,
        "status": appeal.status,
        "telegram_user_id": appeal.telegram_user_id,
    }


@router.get("/appeals")
async def list_appeals(
    _: None = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return pending and resolved appeal records."""
    rows = (await session.scalars(select(AppealRecord).order_by(AppealRecord.id.desc()))).all()
    return [
        {
            "id": appeal.id,
            "telegram_user_id": appeal.telegram_user_id,
            "ban_id": appeal.ban_id,
            "fingerprint_hash": appeal.fingerprint_hash,
            "reason": appeal.reason,
            "status": appeal.status,
            "created_at": appeal.created_at.isoformat() if appeal.created_at else None,
        }
        for appeal in rows
    ]


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
            "status": ban.status,
            "banned_at": ban.banned_at.isoformat() if ban.banned_at else None,
        }
        for ban in rows
    ]
