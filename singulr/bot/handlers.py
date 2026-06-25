"""Telegram bot handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ChatJoinRequestHandler, CommandHandler, ContextTypes, MessageHandler, filters

from singulr.config import get_settings
from singulr.db import SessionLocal
from singulr.models import MessageLog, StylometryProfile
from singulr.services.bans import record_ban as persist_ban
from singulr.services.stylometry import extract_features, merge_feature_vectors
from singulr.services.telegram_actions import (
    ban_member,
    get_channel_title,
    grant_access,
    log_to_channel,
    notify_user_result,
    restrict_member,
    send_verification_dm,
)
from singulr.services.tokens import create_token
from singulr.services.watcher import find_watcher_matches

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manual /verify for users who missed the DM."""
    if not update.effective_user or not update.message:
        return
    settings = get_settings()
    if not settings.channel_id:
        await update.message.reply_text("Singulr is not fully configured yet.")
        return
    async with SessionLocal() as session:
        token = await create_token(session, update.effective_user.id, settings.channel_id)
    url = f"{settings.public_base_url.rstrip('/')}/verify?token={token}"
    await update.message.reply_text(f"Tap to verify:\n{url}")


async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Restrict joiner and send verification DM."""
    request = update.chat_join_request
    if not request or not request.from_user:
        return
    settings = get_settings()
    channel_id = request.chat.id
    user = request.from_user

    try:
        await restrict_member(context.application, channel_id, user.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not restrict member: %s", exc)

    async with SessionLocal() as session:
        token = await create_token(session, user.id, channel_id)

    title = await get_channel_title(context.application, channel_id)
    url = f"{settings.public_base_url.rstrip('/')}/verify?token={token}"
    try:
        await send_verification_dm(context.application, user.id, url, title)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not DM user %s: %s", user.id, exc)


async def on_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log messages for stylometry profiling (The Watcher)."""
    message = update.effective_message
    user = update.effective_user
    if not message or not user or not message.text:
        return
    settings = get_settings()
    if settings.channel_id and update.effective_chat and update.effective_chat.id != settings.channel_id:
        return

    features = extract_features(message.text)
    if not features:
        return

    async with SessionLocal() as session:
        session.add(
            MessageLog(
                telegram_user_id=user.id,
                message_features=features,
            )
        )
        row = await session.get(StylometryProfile, user.id)
        if row:
            vectors = [row.feature_vector, features]
            row.feature_vector = merge_feature_vectors(vectors)
            row.message_count += 1
        else:
            session.add(
                StylometryProfile(
                    telegram_user_id=user.id,
                    feature_vector=features,
                    message_count=1,
                )
            )
        await session.commit()


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline approve/ban from log channel."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    settings = get_settings()
    data = query.data
    if data.startswith("approve_"):
        user_id = int(data.removeprefix("approve_"))
        await grant_access(context.application, settings.channel_id, user_id)
        await notify_user_result(context.application, user_id, approved=True)
        if query.message:
            await query.message.reply_text(f"Approved user {user_id}")
    elif data.startswith("ban_"):
        user_id = int(data.removeprefix("ban_"))
        await ban_member(context.application, settings.channel_id, user_id)
        async with SessionLocal() as session:
            await persist_ban(
                session,
                telegram_user_id=user_id,
                channel_id=settings.channel_id,
                reason="admin_ban",
            )
        await notify_user_result(context.application, user_id, approved=False)
        if query.message:
            await query.message.reply_text(f"Banned user {user_id}")


async def run_watcher_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job comparing member stylometry to banned profiles."""
    async with SessionLocal() as session:
        matches = await find_watcher_matches(session)
    for match in matches:
        await log_to_channel(
            context.application,
            "WATCHER_MATCH",
            user_id=match["user_id"],
            reason=match["reason"],
            match_score=match["score"],
            ban_fingerprint=match["ban_fingerprint"],
        )


def build_bot_application() -> Application:
    """Create configured python-telegram-bot Application."""
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required")

    app = Application.builder().token(settings.bot_token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("verify", start_command))
    app.add_handler(ChatJoinRequestHandler(on_join_request))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(
        MessageHandler(filters.ChatType.CHANNEL & filters.TEXT & ~filters.COMMAND, on_channel_message)
    )

    if app.job_queue:
        app.job_queue.run_repeating(
            run_watcher_job,
            interval=settings.watcher_interval_minutes * 60,
            first=60,
        )

    return app


async def apply_verification_decision(
    app: Application,
    *,
    decision: str,
    telegram_user_id: int,
    channel_id: int,
    reason: str = "",
    risk_factors: list[str] | None = None,
    fingerprint_hash: str | None = None,
) -> None:
    """Execute bot action after verification API returns."""
    if decision == "approve":
        await grant_access(app, channel_id, telegram_user_id)
        await notify_user_result(app, telegram_user_id, approved=True)
        await log_to_channel(
            app,
            "APPROVED",
            f"User {telegram_user_id} verified successfully.",
        )
    elif decision == "flag":
        await log_to_channel(
            app,
            "ELEVATED_RISK",
            user_id=telegram_user_id,
            reason=reason,
            risk_factors=risk_factors,
        )
        await notify_user_result(app, telegram_user_id, approved=False, held=True)
    else:
        await ban_member(app, channel_id, telegram_user_id)
        await notify_user_result(app, telegram_user_id, approved=False)
        event_type = "BAN_EVASION" if "fingerprint" in reason.lower() else "BLOCKED"
        await log_to_channel(
            app,
            event_type,
            body=f"User ID: {telegram_user_id}\nReason: {reason}" if event_type == "BLOCKED" else None,
            user_id=telegram_user_id,
            reason=reason,
            fingerprint_hash=fingerprint_hash,
        )
