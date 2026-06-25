"""Telegram bot handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ChatJoinRequestHandler, CommandHandler, ContextTypes, MessageHandler, filters

from singulr.bot.security_wizard import build_security_wizard_handler
from singulr.bot.ban_flow import (
    PENDING_BAN_CATEGORY_KEY,
    PENDING_BAN_USER_KEY,
    category_keyboard,
    parse_ban_category,
    parse_ban_severity,
    parse_ban_user_id,
    severity_keyboard,
)
from singulr.config import get_settings
from singulr.db import SessionLocal
from singulr.domain.ban_taxonomy import BanCategory
from singulr.models import Ban, MessageLog, Profile, StylometryProfile
from singulr.services.bans import record_ban as persist_ban
from singulr.services.ban_history import format_ban_history_list
from singulr.services.stylometry import extract_features, merge_feature_vectors
from singulr.services.telegram_actions import (
    ban_member,
    format_admin_profile_details,
    get_channel_title,
    grant_access,
    log_to_channel,
    log_to_ops_channel,
    notify_user_denied,
    notify_user_result,
    restrict_member,
    send_verification_dm,
)
from singulr.services.channel_policy import get_effective_channel_policy
from singulr.services.reverification import require_reverification
from singulr.services.social_profile import SocialProfileContext, analyze_social_profile
from singulr.services.tokens import TokenRateLimitError, create_token
from sqlalchemy import select
from singulr.services.watcher import find_watcher_matches

logger = logging.getLogger(__name__)


async def _ban_history_for_fingerprint(fingerprint_hash: str | None) -> str | None:
    """Load formatted ban history for admin review cards."""
    if not fingerprint_hash:
        return None
    async with SessionLocal() as session:
        rows = (
            await session.scalars(select(Ban).where(Ban.fingerprint_hash == fingerprint_hash))
        ).all()
    if not rows:
        return None
    return format_ban_history_list(list(rows))


def _parse_channel_user_callback(payload: str) -> tuple[int, int]:
    """Parse `{channel_id}_{user_id}` callback payloads."""
    settings = get_settings()
    if "_" in payload:
        channel_part, user_part = payload.rsplit("_", 1)
        return int(channel_part), int(user_part)
    return settings.channel_id, int(payload)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manual /verify for users who missed the DM."""
    if not update.effective_user or not update.message:
        return
    settings = get_settings()
    if not settings.channel_id:
        await update.message.reply_text("Singulr is not fully configured yet.")
        return
    try:
        async with SessionLocal() as session:
            token = await create_token(session, update.effective_user.id, settings.channel_id)
    except TokenRateLimitError:
        await update.message.reply_text(
            "You have requested too many verification links today. "
            "Please try again later or contact the channel admin."
        )
        return
    url = f"{settings.public_base_url.rstrip('/')}/verify?token={token}"
    await update.message.reply_text(f"Tap to verify:\n{url}")


def _is_bot_admin(user_id: int) -> bool:
    """True when the Telegram user is the configured Singulr admin."""
    admin_id = get_settings().admin_telegram_id
    return bool(admin_id) and user_id == admin_id


async def reverify_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to flag a member for mandatory reverification."""
    if not update.effective_user or not update.message:
        return
    if not _is_bot_admin(update.effective_user.id):
        await update.message.reply_text("Only the configured admin may use /reverify.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /reverify <telegram_user_id>")
        return
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Usage: /reverify <telegram_user_id>")
        return

    async with SessionLocal() as session:
        profile = await require_reverification(session, target_user_id)
    if not profile:
        await update.message.reply_text(f"No profile found for user {target_user_id}.")
        return
    await update.message.reply_text(
        f"User {target_user_id} flagged for reverification. "
        "They will receive a new verify link on their next join request."
    )


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

    title = await get_channel_title(context.application, channel_id)
    display_name = " ".join(part for part in (user.first_name, user.last_name) if part)

    try:
        async with SessionLocal() as session:
            token = await create_token(
                session,
                user.id,
                channel_id,
                join_username=user.username,
                join_display_name=display_name or None,
                join_language_code=user.language_code,
                join_channel_title=title,
            )
    except TokenRateLimitError:
        try:
            await context.application.bot.send_message(
                chat_id=user.id,
                text=(
                    "You have requested too many verification links today. "
                    "Please try again later or contact the channel admin."
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not DM rate-limited user %s: %s", user.id, exc)
        return

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
    elif data.startswith("permit_"):
        channel_id, user_id = _parse_channel_user_callback(data.removeprefix("permit_"))
        await grant_access(context.application, channel_id, user_id)
        await notify_user_result(context.application, user_id, approved=True)
        if query.message:
            await query.message.reply_text(f"Permitted user {user_id}")
    elif data.startswith("deny_"):
        channel_id, user_id = _parse_channel_user_callback(data.removeprefix("deny_"))
        await ban_member(context.application, channel_id, user_id)
        await notify_user_denied(
            context.application,
            user_id,
            "Admin review denied your verification.",
        )
        if query.message:
            await query.message.reply_text(f"Denied user {user_id}")
    elif data.startswith("details_"):
        channel_id, user_id = _parse_channel_user_callback(data.removeprefix("details_"))
        fingerprint_hash = None
        social_summary = None
        social_signals: list[str] = []
        social_sources: list[str] = []
        async with SessionLocal() as session:
            profile = await session.scalar(
                select(Profile).where(Profile.telegram_user_id == user_id)
            )
            if profile:
                fingerprint_hash = profile.fingerprint_hash
            policy = await get_effective_channel_policy(session, channel_id)
            ctx = SocialProfileContext(
                telegram_user_id=user_id,
                channel_id=channel_id,
            )
            try:
                member = await context.application.bot.get_chat_member(channel_id, user_id)
                user = member.user
                ctx = SocialProfileContext(
                    telegram_user_id=user_id,
                    channel_id=channel_id,
                    username=user.username,
                    display_name=" ".join(
                        part for part in (user.first_name, user.last_name) if part
                    )
                    or None,
                    language_code=user.language_code,
                    channel_title=await get_channel_title(context.application, channel_id),
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                social = await analyze_social_profile(
                    session,
                    ctx,
                    policy=policy,
                    refresh=False,
                )
                await session.commit()
            except Exception:  # noqa: BLE001
                social = None
            if social:
                social_summary = social.summary or None
                social_signals = list(social.soft_signals)
                social_sources = list(social.sources)
        ban_history = await _ban_history_for_fingerprint(fingerprint_hash)
        body = await format_admin_profile_details(
            context.application,
            user_id=user_id,
            channel_id=channel_id,
            ban_history=ban_history,
            social_summary=social_summary,
            social_signals=social_signals,
            social_sources=social_sources,
        )
        if query.message:
            await query.message.reply_text(body)
    elif data.startswith("ban_sev_"):
        severity = parse_ban_severity(data)
        user_id = context.user_data.pop(PENDING_BAN_USER_KEY, None)
        category_value = context.user_data.pop(PENDING_BAN_CATEGORY_KEY, None)
        if severity is None or user_id is None or category_value is None:
            if query.message:
                await query.message.reply_text("Ban flow expired — tap Ban again.")
            return
        try:
            category = BanCategory(category_value)
        except ValueError:
            if query.message:
                await query.message.reply_text("Invalid ban category — start again.")
            return
        await ban_member(context.application, settings.channel_id, user_id)
        async with SessionLocal() as session:
            await persist_ban(
                session,
                telegram_user_id=user_id,
                channel_id=settings.channel_id,
                reason="admin_ban",
                category=category,
                severity=severity,
            )
        await notify_user_result(context.application, user_id, approved=False)
        if query.message:
            await query.message.reply_text(
                f"Banned user {user_id} ({category.value}/{severity.value})."
            )
    elif data.startswith("ban_cat_"):
        category = parse_ban_category(data)
        if category is None or PENDING_BAN_USER_KEY not in context.user_data:
            if query.message:
                await query.message.reply_text("Ban flow expired — tap Ban again.")
            return
        context.user_data[PENDING_BAN_CATEGORY_KEY] = category.value
        if query.message:
            await query.message.reply_text(
                f"Ban user {context.user_data[PENDING_BAN_USER_KEY]} — choose severity:",
                reply_markup=severity_keyboard(),
            )
    elif (user_id := parse_ban_user_id(data)) is not None:
        context.user_data[PENDING_BAN_USER_KEY] = user_id
        if query.message:
            await query.message.reply_text(
                f"Ban user {user_id} — choose category:",
                reply_markup=category_keyboard(),
            )


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
    app.add_handler(build_security_wizard_handler())
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("verify", start_command))
    app.add_handler(CommandHandler("reverify", reverify_command))
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
    admin_ops_chat_id: int | None = None,
    matched_ban_id: int | None = None,
) -> None:
    """Execute bot action after verification API returns."""
    ban_history = await _ban_history_for_fingerprint(fingerprint_hash)
    if decision == "approve":
        await grant_access(app, channel_id, telegram_user_id)
        await notify_user_result(
            app, telegram_user_id, approved=True, channel_id=channel_id
        )
        await log_to_ops_channel(
            app,
            "APPROVED",
            channel_id=channel_id,
            admin_ops_chat_id=admin_ops_chat_id,
            body=f"User {telegram_user_id} verified successfully.",
            user_id=telegram_user_id,
        )
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
        await log_to_ops_channel(
            app,
            "ELEVATED_RISK",
            channel_id=channel_id,
            admin_ops_chat_id=admin_ops_chat_id,
            user_id=telegram_user_id,
            reason=reason,
            risk_factors=risk_factors,
            include_details_button=True,
            ban_history=ban_history,
        )
        await notify_user_result(app, telegram_user_id, approved=False, held=True)
    elif decision == "pending":
        await log_to_ops_channel(
            app,
            "PENDING_REVIEW",
            channel_id=channel_id,
            admin_ops_chat_id=admin_ops_chat_id,
            user_id=telegram_user_id,
            reason=reason,
            risk_factors=risk_factors,
            matched_ban_id=matched_ban_id,
            ban_history=ban_history,
            include_details_button=True,
        )
        await notify_user_result(app, telegram_user_id, approved=False, held=True)
    else:
        await ban_member(app, channel_id, telegram_user_id)
        await notify_user_result(app, telegram_user_id, approved=False)
        event_type = "BAN_EVASION" if "evasion" in reason.lower() else "BLOCKED"
        await log_to_ops_channel(
            app,
            event_type,
            channel_id=channel_id,
            admin_ops_chat_id=admin_ops_chat_id,
            user_id=telegram_user_id,
            reason=reason,
            fingerprint_hash=fingerprint_hash,
            ban_history=ban_history,
            include_details_button=True,
        )
