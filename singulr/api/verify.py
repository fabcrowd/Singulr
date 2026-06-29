"""FastAPI routes for verification flow."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.api.security import require_admin_key

from singulr.bot.handlers import apply_verification_decision
from singulr.bot.runtime import get_application
from singulr.config import VERIFICATION_SENTENCE, get_settings
from singulr.db import get_session
from singulr.models import IPSession, Profile
from singulr.services.bans import record_ban as persist_ban
from singulr.services.client_ip import resolve_client_ip
from singulr.services.blockchain import ChainClient
from singulr.services.channel_policy import EffectivePolicy, get_effective_channel_policy
from singulr.services.hashing import hash_fingerprint, hash_ip
from singulr.services.keystroke import build_keystroke_profile
from singulr.services.matching import Decision, MatchResult, check_known_bad
from singulr.services.reverification import STATUS_APPROVED, get_profile, is_reverification_required
from singulr.services.rate_limit import allow_precheck_for_token, allow_verify_request
from singulr.services.tokens import validate_token, claim_verification_token
from singulr.services.keystroke_validation import submit_body_too_large
from singulr.services.verify_ban import block_ban_taxonomy
from singulr.services.verify_session import (
    issue_challenge_secret,
    verify_challenge_proof,
)

router = APIRouter(prefix="/api", tags=["verify"])
_chain = ChainClient()
logger = logging.getLogger(__name__)


class PrecheckBody(BaseModel):
    """Pre-render chain and registry check."""

    token: str
    visitor_id: str
    request_id: str | None = None


class EnvFlags(BaseModel):
    """Browser environment signals from verify.js."""

    webdriver: bool = False
    headless_ua: bool = False
    plugins_count: int | None = None
    languages_count: int | None = None
    webgl_renderer: str | None = None
    outer_dims_zero: bool = False


class SubmitBody(BaseModel):
    """Full verification submission."""

    token: str
    visitor_id: str
    request_id: str | None = None
    device_type: str = Field(pattern="^(mobile|desktop)$")
    typed_text: str = Field(max_length=2048)
    keystrokes: list[dict[str, Any]] = Field(max_length=500)
    wpm: float | None = None
    error_count: int = 0
    privacy_accepted: bool = False
    env_flags: EnvFlags | None = None
    challenge_proof: str = ""


class InternalBanBody(BaseModel):
    """Request body for the internal ban endpoint."""

    telegram_user_id: int
    channel_id: int = 0
    reason: str = "admin_ban"


def _client_ip(request: Request) -> str:
    """Extract client IP from proxy headers or socket."""
    settings = get_settings()
    return resolve_client_ip(request, settings.trusted_proxy_ip_list)


def _enforce_verify_rate_limit(request: Request) -> None:
    """Raise 429 when the client IP exceeds the verify rate limit."""
    settings = get_settings()
    if not allow_verify_request(
        _client_ip(request),
        limit_per_minute=settings.verify_rate_limit_per_minute,
    ):
        raise HTTPException(status_code=429, detail="rate_limited")


def _allow_visitor_id_rebind(bound: str, visitor_id: str) -> bool:
    """Allow upgrading from fallback fingerprint visitor id to FingerprintJS id."""
    return bound.startswith("fb_") and not visitor_id.startswith("fb_")


def _bind_precheck_visitor_id(token_row: Any, visitor_id: str) -> None:
    """Record or validate visitor_id on the token during precheck."""
    bound = token_row.bound_visitor_id
    if bound is None:
        token_row.bound_visitor_id = visitor_id
        return
    if bound == visitor_id:
        return
    if _allow_visitor_id_rebind(bound, visitor_id):
        token_row.bound_visitor_id = visitor_id
        return
    raise HTTPException(status_code=400, detail="visitor_id_mismatch")


def _enforce_precheck_token_rate_limit(token: str) -> None:
    """Raise 429 when precheck for this token exceeds the per-token rate limit."""
    settings = get_settings()
    if not allow_precheck_for_token(
        token,
        limit_per_minute=settings.verify_precheck_per_token_per_minute,
    ):
        raise HTTPException(status_code=429, detail="rate_limited")


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
        admin_ops_chat_id=payload.get("admin_ops_chat_id"),
        matched_ban_id=payload.get("matched_ban_id"),
    )


def _decision_name(result: MatchResult) -> str:
    """Map matching engine decision to API and bot payload names."""
    if result.decision == Decision.BLOCK:
        return "block"
    if result.decision == Decision.PENDING:
        return "pending"
    if result.decision == Decision.FLAG:
        return "flag"
    return "approve"


def _decision_payload(
    *,
    decision: str,
    telegram_user_id: int,
    channel_id: int,
    policy: EffectivePolicy,
    result: MatchResult | None = None,
    fingerprint_hash: str | None = None,
) -> dict[str, Any]:
    """Build notify-bot payload with channel policy audit fields."""
    payload: dict[str, Any] = {
        "decision": decision,
        "telegram_user_id": telegram_user_id,
        "channel_id": channel_id,
        "security_preset": policy.security_preset,
    }
    if result:
        if result.reason:
            payload["reason"] = result.reason
        if result.risk_factors:
            payload["risk_factors"] = result.risk_factors
        if result.matched_ban_id is not None:
            payload["matched_ban_id"] = result.matched_ban_id
    if fingerprint_hash:
        payload["fingerprint_hash"] = fingerprint_hash
    if policy.admin_ops_chat_id:
        payload["admin_ops_chat_id"] = policy.admin_ops_chat_id
    return payload


def _log_verification_decision(
    *,
    telegram_user_id: int,
    channel_id: int,
    decision: str,
    policy: EffectivePolicy,
    source: str,
) -> None:
    """Record decision audit fields including effective security preset."""
    logger.info(
        "verification_decision source=%s user=%s channel=%s decision=%s security_preset=%s",
        source,
        telegram_user_id,
        channel_id,
        decision,
        policy.security_preset,
    )


@router.post("/verify/precheck")
async def precheck(
    body: PrecheckBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run ban checks before rendering the verification form."""
    _enforce_verify_rate_limit(request)
    _enforce_precheck_token_rate_limit(body.token)
    token_row = await validate_token(session, body.token)
    if not token_row:
        raise HTTPException(status_code=410, detail="link_expired")

    _bind_precheck_visitor_id(token_row, body.visitor_id)

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

    policy = await get_effective_channel_policy(session, token_row.channel_id)
    result = await check_known_bad(
        session,
        _chain,
        telegram_user_id=token_row.telegram_user_id,
        fingerprint_hash=fingerprint_hash,
        ip_hash=ip_hash,
        channel_id=token_row.channel_id,
        policy=policy,
        token_row=token_row,
    )

    if result.decision == Decision.BLOCK:
        return {"allowed": False, "reason": "unavailable"}

    challenge_secret = issue_challenge_secret()
    token_row.verify_challenge_secret = challenge_secret
    await session.commit()

    return {
        "allowed": True,
        "sentence": VERIFICATION_SENTENCE,
        "fingerprint_public_key": get_settings().fingerprint_public_key or None,
        "challenge_secret": challenge_secret,
    }


@router.post("/verify/submit")
async def submit(
    body: SubmitBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Process verification, notify bot, and return decision."""
    _enforce_verify_rate_limit(request)
    if submit_body_too_large(body.model_dump()):
        raise HTTPException(status_code=413, detail="payload_too_large")
    if not body.privacy_accepted:
        raise HTTPException(status_code=400, detail="privacy_required")

    if body.typed_text.strip() != VERIFICATION_SENTENCE:
        raise HTTPException(status_code=400, detail="sentence_mismatch")

    token_row = await validate_token(session, body.token)
    if not token_row:
        raise HTTPException(status_code=410, detail="link_expired")

    if not verify_challenge_proof(
        token_row.verify_challenge_secret,
        body.challenge_proof,
        token=body.token,
        visitor_id=body.visitor_id,
    ):
        raise HTTPException(status_code=400, detail="challenge_invalid")

    policy = await get_effective_channel_policy(session, token_row.channel_id)
    visitor_mismatch = bool(
        token_row.bound_visitor_id
        and token_row.bound_visitor_id != body.visitor_id
    )
    if visitor_mismatch and policy.security_preset == "strict":
        raise HTTPException(status_code=400, detail="visitor_id_mismatch")

    token_row = await claim_verification_token(session, body.token)
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

    if visitor_mismatch:
        result = MatchResult(
            Decision.PENDING,
            "Visitor fingerprint mismatch",
            ["visitor_id_mismatch"],
        )
    else:
        result = await check_known_bad(
            session,
            _chain,
            telegram_user_id=token_row.telegram_user_id,
            fingerprint_hash=fingerprint_hash,
            ip_hash=ip_hash,
            keystroke_profile=keystroke_profile,
            env_flags=env_flags,
            channel_id=token_row.channel_id,
            policy=policy,
            token_row=token_row,
        )

    session.add(
        IPSession(
            ip_hash=ip_hash,
            telegram_user_id=token_row.telegram_user_id,
            channel_id=token_row.channel_id,
            action=result.decision.value,
        )
    )
    await session.commit()

    decision_name = _decision_name(result)
    _log_verification_decision(
        telegram_user_id=token_row.telegram_user_id,
        channel_id=token_row.channel_id,
        decision=decision_name,
        policy=policy,
        source="submit",
    )

    if result.decision == Decision.BLOCK:
        category, severity, ban_reason = block_ban_taxonomy(result)
        await persist_ban(
            session,
            telegram_user_id=token_row.telegram_user_id,
            channel_id=token_row.channel_id,
            reason=ban_reason,
            category=category,
            severity=severity,
        )
        payload = _decision_payload(
            decision="block",
            telegram_user_id=token_row.telegram_user_id,
            channel_id=token_row.channel_id,
            policy=policy,
            result=result,
            fingerprint_hash=fingerprint_hash,
        )
        await _notify_bot(payload)
        return {"decision": "block"}

    if result.decision in {Decision.FLAG, Decision.PENDING}:
        payload = _decision_payload(
            decision=decision_name,
            telegram_user_id=token_row.telegram_user_id,
            channel_id=token_row.channel_id,
            policy=policy,
            result=result,
        )
        await _notify_bot(payload)
        return {"decision": decision_name}

    existing_profile = await get_profile(
        session, token_row.telegram_user_id, device_type=body.device_type
    )
    if existing_profile:
        existing_profile.fingerprint_hash = fingerprint_hash
        existing_profile.keystroke_profile = keystroke_profile
        existing_profile.ip_hash = ip_hash
        if is_reverification_required(existing_profile):
            existing_profile.status = STATUS_APPROVED
    else:
        session.add(
            Profile(
                telegram_user_id=token_row.telegram_user_id,
                fingerprint_hash=fingerprint_hash,
                keystroke_profile=keystroke_profile,
                device_type=body.device_type,
                ip_hash=ip_hash,
                status=STATUS_APPROVED,
            )
        )
    await session.commit()

    if policy.network_registry_mode != "off":
        await _chain.register_fingerprint(fingerprint_hash, token_row.channel_id)

    _log_verification_decision(
        telegram_user_id=token_row.telegram_user_id,
        channel_id=token_row.channel_id,
        decision="approve",
        policy=policy,
        source="submit",
    )
    payload = _decision_payload(
        decision="approve",
        telegram_user_id=token_row.telegram_user_id,
        channel_id=token_row.channel_id,
        policy=policy,
    )
    await _notify_bot(payload)
    return {"decision": "approve"}


@router.post("/internal/ban")
async def admin_ban(
    body: InternalBanBody,
    _: None = Depends(require_admin_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Record a ban from admin inline button."""
    fingerprint_hash = await persist_ban(
        session,
        telegram_user_id=body.telegram_user_id,
        channel_id=body.channel_id,
        reason=body.reason,
    )
    return {"ok": True, "fingerprint_hash": fingerprint_hash}
