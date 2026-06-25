"""FastAPI routes for verification flow."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.bot.handlers import apply_verification_decision
from singulr.bot.runtime import get_application
from singulr.config import VERIFICATION_SENTENCE, get_settings
from singulr.db import get_session
from singulr.models import Ban, IPSession, Profile
from singulr.services.bans import record_ban as persist_ban
from singulr.services.blockchain import ChainClient
from singulr.services.hashing import hash_fingerprint, hash_ip
from singulr.services.keystroke import build_keystroke_profile
from singulr.services.matching import Decision, check_known_bad
from singulr.services.tokens import mark_token_used, validate_token

router = APIRouter(prefix="/api", tags=["verify"])
_chain = ChainClient()


class PrecheckBody(BaseModel):
    """Pre-render chain and registry check."""

    token: str
    visitor_id: str
    request_id: str | None = None


class EnvFlags(BaseModel):
    """Browser environment signals from verify.js."""

    webdriver: bool = False
    headless_ua: bool = False


class SubmitBody(BaseModel):
    """Full verification submission."""

    token: str
    visitor_id: str
    request_id: str | None = None
    device_type: str = Field(pattern="^(mobile|desktop)$")
    typed_text: str
    keystrokes: list[dict[str, Any]]
    wpm: float | None = None
    error_count: int = 0
    privacy_accepted: bool = False
    env_flags: EnvFlags | None = None


def _client_ip(request: Request) -> str:
    """Extract client IP from proxy headers or socket."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "0.0.0.0"


async def _notify_bot(payload: dict[str, Any]) -> None:
    """Apply Telegram bot action when verification completes."""
    app = get_application()
    if not app:
        return
    await apply_verification_decision(
        app,
        decision=payload["decision"],
        telegram_user_id=int(payload["telegram_user_id"]),
        channel_id=int(payload["channel_id"]),
        reason=payload.get("reason", ""),
        risk_factors=payload.get("risk_factors"),
        fingerprint_hash=payload.get("fingerprint_hash"),
    )


@router.post("/verify/precheck")
async def precheck(
    body: PrecheckBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run ban checks before rendering the verification form."""
    token_row = await validate_token(session, body.token)
    if not token_row:
        raise HTTPException(status_code=410, detail="link_expired")

    fingerprint_hash = hash_fingerprint(body.visitor_id, body.request_id)
    ip_hash = hash_ip(_client_ip(request))

    session.add(
        IPSession(
            ip_hash=ip_hash,
            telegram_user_id=token_row.telegram_user_id,
            channel_id=token_row.channel_id,
            action="opened",
        )
    )
    await session.commit()

    result = await check_known_bad(
        session,
        _chain,
        telegram_user_id=token_row.telegram_user_id,
        fingerprint_hash=fingerprint_hash,
        ip_hash=ip_hash,
    )

    if result.decision == Decision.BLOCK:
        return {"allowed": False, "reason": "unavailable"}

    return {
        "allowed": True,
        "sentence": VERIFICATION_SENTENCE,
        "fingerprint_public_key": get_settings().fingerprint_public_key or None,
        "ip_flagged": "ip_hash_match" in result.risk_factors,
    }


@router.post("/verify/submit")
async def submit(
    body: SubmitBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Process verification, notify bot, and return decision."""
    if not body.privacy_accepted:
        raise HTTPException(status_code=400, detail="privacy_required")

    if body.typed_text.strip() != VERIFICATION_SENTENCE:
        raise HTTPException(status_code=400, detail="sentence_mismatch")

    token_row = await validate_token(session, body.token)
    if not token_row:
        raise HTTPException(status_code=410, detail="link_expired")

    fingerprint_hash = hash_fingerprint(body.visitor_id, body.request_id)
    ip_hash = hash_ip(_client_ip(request))
    keystroke_profile = build_keystroke_profile(
        body.keystrokes,
        body.device_type,
        wpm=body.wpm,
        error_count=body.error_count,
    )
    env_flags = body.env_flags.model_dump() if body.env_flags else None

    result = await check_known_bad(
        session,
        _chain,
        telegram_user_id=token_row.telegram_user_id,
        fingerprint_hash=fingerprint_hash,
        ip_hash=ip_hash,
        keystroke_profile=keystroke_profile,
        env_flags=env_flags,
    )

    await mark_token_used(session, body.token)

    session.add(
        IPSession(
            ip_hash=ip_hash,
            telegram_user_id=token_row.telegram_user_id,
            channel_id=token_row.channel_id,
            action=result.decision.value,
        )
    )
    await session.commit()

    if result.decision == Decision.BLOCK:
        ban = Ban(
            telegram_user_id=token_row.telegram_user_id,
            fingerprint_hash=fingerprint_hash,
            ip_hash=ip_hash,
            reason=result.reason,
        )
        session.add(ban)
        await session.commit()
        tx = await _chain.record_ban(fingerprint_hash, None, token_row.channel_id)
        if tx:
            ban.chain_tx = tx
            await session.commit()
        payload = {
            "decision": "block",
            "telegram_user_id": token_row.telegram_user_id,
            "channel_id": token_row.channel_id,
            "reason": result.reason,
            "fingerprint_hash": fingerprint_hash,
        }
        await _notify_bot(payload)
        return payload

    if result.decision == Decision.FLAG:
        payload = {
            "decision": "flag",
            "telegram_user_id": token_row.telegram_user_id,
            "channel_id": token_row.channel_id,
            "reason": result.reason,
            "risk_factors": result.risk_factors,
        }
        await _notify_bot(payload)
        return payload

    profile = Profile(
        telegram_user_id=token_row.telegram_user_id,
        fingerprint_hash=fingerprint_hash,
        keystroke_profile=keystroke_profile,
        device_type=body.device_type,
        ip_hash=ip_hash,
        status="approved",
    )
    session.add(profile)
    await session.commit()

    payload = {
        "decision": "approve",
        "telegram_user_id": token_row.telegram_user_id,
        "channel_id": token_row.channel_id,
    }
    await _notify_bot(payload)
    return payload


@router.post("/internal/ban")
async def admin_ban(
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Record a ban from admin inline button."""
    fingerprint_hash = await persist_ban(
        session,
        telegram_user_id=int(payload["telegram_user_id"]),
        channel_id=int(payload.get("channel_id", 0)),
        reason=str(payload.get("reason", "admin_ban")),
    )
    return {"ok": True, "fingerprint_hash": fingerprint_hash}
