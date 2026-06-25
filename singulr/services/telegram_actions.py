"""Telegram API helpers for channel access and logging."""

from __future__ import annotations

import logging

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from singulr.config import get_settings

logger = logging.getLogger(__name__)


async def restrict_member(app: Application, channel_id: int, user_id: int) -> None:
    """Restrict a user until verification completes."""
    await app.bot.restrict_chat_member(
        chat_id=channel_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False, can_send_audios=False),
    )


async def grant_access(app: Application, channel_id: int, user_id: int) -> None:
    """Grant full channel access after approval."""
    await app.bot.restrict_chat_member(
        chat_id=channel_id,
        user_id=user_id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_invite_users=False,
        ),
    )


async def ban_member(app: Application, channel_id: int, user_id: int) -> None:
    """Permanently ban a user from the channel."""
    await app.bot.ban_chat_member(chat_id=channel_id, user_id=user_id)


async def send_verification_dm(
    app: Application,
    user_id: int,
    verify_url: str,
    channel_name: str,
) -> None:
    """DM the user a one-time verification link."""
    text = (
        f"Welcome! **{channel_name}** uses Singulr to keep membership trusted.\n\n"
        f"Tap below to verify - takes about 15 seconds.\n\n"
        f"[Verify Membership]({verify_url})\n\n"
        f"_Link expires in {get_settings().token_expiry_minutes} minutes._"
    )
    await app.bot.send_message(
        chat_id=user_id,
        text=text,
        parse_mode="Markdown",
        disable_web_page_preview=False,
    )


async def notify_user_result(app: Application, user_id: int, approved: bool, held: bool = False) -> None:
    """Tell the user the verification outcome."""
    if approved:
        text = "Verification complete. Welcome to the channel!"
    elif held:
        text = "Your verification is under review. An admin will approve shortly."
    else:
        text = "This verification link is no longer available. Contact the channel admin if you believe this is an error."
    await app.bot.send_message(chat_id=user_id, text=text)


FINGERPRINT_DISPLAY_LEN = 18


def truncate_fingerprint_hash(fingerprint_hash: str) -> str:
    """Return a short fingerprint prefix for admin log messages."""
    if len(fingerprint_hash) <= FINGERPRINT_DISPLAY_LEN:
        return fingerprint_hash
    return f"{fingerprint_hash[:FINGERPRINT_DISPLAY_LEN]}..."


def _risk_score_from_factors(risk_factors: list[str]) -> float | None:
    """Extract the highest similarity score encoded in risk factor labels."""
    scores: list[float] = []
    for factor in risk_factors:
        if ":" not in factor:
            continue
        label, _, raw = factor.partition(":")
        if not label.endswith("_similarity"):
            continue
        try:
            scores.append(float(raw))
        except ValueError:
            continue
    return max(scores) if scores else None


def format_elevated_risk_body(
    *,
    user_id: int,
    reason: str,
    risk_factors: list[str] | None = None,
) -> str:
    """Build admin log body for elevated-risk verification holds."""
    factors = risk_factors or []
    lines = [
        f"User ID: {user_id}",
        f"Reason: {reason}",
    ]
    if factors:
        lines.append(f"Risk factors: {', '.join(factors)}")
    risk_score = _risk_score_from_factors(factors)
    if risk_score is not None:
        lines.append(f"Risk score: {risk_score:.0%}")
    return "\n".join(lines)


def format_pending_review_body(
    *,
    user_id: int,
    reason: str,
    risk_factors: list[str] | None = None,
    matched_ban_id: int | None = None,
) -> str:
    """Build ops channel body for pending ban-evasion review."""
    body = format_elevated_risk_body(
        user_id=user_id,
        reason=reason,
        risk_factors=risk_factors,
    )
    if matched_ban_id is not None:
        body = f"{body}\nMatched ban ID: {matched_ban_id}"
    return body


def format_ban_evasion_body(
    *,
    user_id: int,
    reason: str,
    fingerprint_hash: str | None = None,
) -> str:
    """Build admin log body for ban-evasion blocks."""
    lines = [
        f"User ID: {user_id}",
        f"Reason: {reason}",
    ]
    if fingerprint_hash:
        lines.append(f"Fingerprint: {truncate_fingerprint_hash(fingerprint_hash)}")
    return "\n".join(lines)


def format_watcher_match_body(
    *,
    user_id: int,
    score: float,
    reason: str,
    ban_fingerprint: str,
) -> str:
    """Build admin log body for watcher stylometry matches."""
    return "\n".join(
        [
            f"User ID: {user_id}",
            f"Match score: {score:.0%}",
            f"Reason: {reason}",
            f"Ban fingerprint: {truncate_fingerprint_hash(ban_fingerprint)}",
        ]
    )


def _build_log_body(
    event_type: str,
    *,
    body: str | None,
    user_id: int | None,
    reason: str | None,
    risk_factors: list[str] | None,
    fingerprint_hash: str | None,
    match_score: float | None,
    ban_fingerprint: str | None,
    matched_ban_id: int | None = None,
) -> str:
    """Resolve the message body for a log channel event."""
    if event_type == "ELEVATED_RISK" and user_id is not None:
        return format_elevated_risk_body(
            user_id=user_id,
            reason=reason or "",
            risk_factors=risk_factors,
        )
    if event_type == "PENDING_REVIEW" and user_id is not None:
        return format_pending_review_body(
            user_id=user_id,
            reason=reason or "",
            risk_factors=risk_factors,
            matched_ban_id=matched_ban_id,
        )
    if event_type == "BAN_EVASION" and user_id is not None:
        return format_ban_evasion_body(
            user_id=user_id,
            reason=reason or body or "",
            fingerprint_hash=fingerprint_hash,
        )
    if event_type == "WATCHER_MATCH" and user_id is not None and match_score is not None and ban_fingerprint:
        return format_watcher_match_body(
            user_id=user_id,
            score=match_score,
            reason=reason or "",
            ban_fingerprint=ban_fingerprint,
        )
    return body or ""


async def notify_user_denied(app: Application, user_id: int, reason: str) -> None:
    """Tell the user their join request was denied with a reason."""
    text = f"Your join request was denied.\n\nReason: {reason}"
    await app.bot.send_message(chat_id=user_id, text=text)


async def resolve_admin_ops_chat_id(
    channel_id: int,
    *,
    override: int | None = None,
) -> int | None:
    """Resolve ops chat from override, env, or per-channel policy."""
    if override:
        return override
    settings = get_settings()
    if settings.admin_ops_chat_id:
        return settings.admin_ops_chat_id
    from singulr.db import SessionLocal
    from singulr.services.channel_policy import get_effective_channel_policy

    async with SessionLocal() as session:
        policy = await get_effective_channel_policy(session, channel_id)
        return policy.admin_ops_chat_id


async def log_to_ops_channel(
    app: Application,
    event_type: str,
    *,
    channel_id: int,
    admin_ops_chat_id: int | None = None,
    body: str | None = None,
    user_id: int | None = None,
    reason: str | None = None,
    risk_factors: list[str] | None = None,
    fingerprint_hash: str | None = None,
    matched_ban_id: int | None = None,
) -> None:
    """Post structured alert to the admin ops channel with optional Permit/Deny actions."""
    ops_chat = await resolve_admin_ops_chat_id(channel_id, override=admin_ops_chat_id)
    if not ops_chat:
        return
    prefix = {
        "PENDING_REVIEW": "PENDING REVIEW",
        "BAN_EVASION": "BAN EVASION",
        "BLOCKED": "BLOCKED",
    }.get(event_type, event_type)
    message_body = _build_log_body(
        event_type,
        body=body,
        user_id=user_id,
        reason=reason,
        risk_factors=risk_factors,
        fingerprint_hash=fingerprint_hash,
        match_score=None,
        ban_fingerprint=None,
        matched_ban_id=matched_ban_id,
    )
    message = f"{prefix}\n\n{message_body}"
    keyboard = None
    if user_id and event_type == "PENDING_REVIEW":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Permit", callback_data=f"permit_{channel_id}_{user_id}"),
                    InlineKeyboardButton("Deny", callback_data=f"deny_{channel_id}_{user_id}"),
                ]
            ]
        )
    try:
        await app.bot.send_message(
            chat_id=ops_chat,
            text=message,
            reply_markup=keyboard,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to log to ops channel: %s", exc)


async def log_to_channel(
    app: Application,
    event_type: str,
    body: str | None = None,
    *,
    user_id: int | None = None,
    reason: str | None = None,
    risk_factors: list[str] | None = None,
    fingerprint_hash: str | None = None,
    match_score: float | None = None,
    ban_fingerprint: str | None = None,
) -> None:
    """Post structured alert to the admin log channel."""
    settings = get_settings()
    if not settings.log_channel_id:
        return
    prefix = {
        "ELEVATED_RISK": "ELEVATED RISK",
        "BAN_EVASION": "BAN EVASION",
        "WATCHER_MATCH": "WATCHER MATCH",
        "APPROVED": "VERIFIED",
        "BLOCKED": "BLOCKED",
    }.get(event_type, event_type)
    message_body = _build_log_body(
        event_type,
        body=body,
        user_id=user_id,
        reason=reason,
        risk_factors=risk_factors,
        fingerprint_hash=fingerprint_hash,
        match_score=match_score,
        ban_fingerprint=ban_fingerprint,
    )
    message = f"{prefix}\n\n{message_body}"
    keyboard = None
    if user_id and event_type in {"ELEVATED_RISK", "WATCHER_MATCH"}:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Approve", callback_data=f"approve_{user_id}"),
                    InlineKeyboardButton("Ban", callback_data=f"ban_{user_id}"),
                ]
            ]
        )
    try:
        await app.bot.send_message(
            chat_id=settings.log_channel_id,
            text=message,
            reply_markup=keyboard,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to log to channel: %s", exc)


async def get_channel_title(app: Application, channel_id: int) -> str:
    """Fetch channel display name."""
    try:
        chat = await app.bot.get_chat(channel_id)
        return chat.title or "your community"
    except Exception:  # noqa: BLE001
        return "your community"
