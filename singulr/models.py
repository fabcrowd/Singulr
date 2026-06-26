"""ORM models for profiles, bans, tokens, and messages."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from singulr.db import Base
from singulr.domain.ban_taxonomy import BanCategory, BanSeverity


class VerificationToken(Base):
    """One-time token tying a Telegram user to a verification session."""

    __tablename__ = "tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    join_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    join_display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    join_language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    join_channel_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    social_profile_cache: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    social_analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Profile(Base):
    """Verified member profile with device and keystroke data."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(66), index=True)
    keystroke_profile: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    device_type: Mapped[str] = mapped_column(String(16))
    ip_hash: Mapped[str | None] = mapped_column(String(66), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="approved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ban(Base):
    """Local ban registry mirrored to chain when configured."""

    __tablename__ = "bans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(66), unique=True, index=True)
    stylometry_hash: Mapped[str | None] = mapped_column(String(66), nullable=True, index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(66), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(
        String(32), default=BanCategory.OTHER.value, server_default=BanCategory.OTHER.value
    )
    severity: Mapped[str] = mapped_column(
        String(16), default=BanSeverity.MEDIUM.value, server_default=BanSeverity.MEDIUM.value
    )
    banned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    chain_tx: Mapped[str | None] = mapped_column(String(80), nullable=True)
    chain_ban_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    overturned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppealRecord(Base):
    """Pending or resolved reinstatement appeal."""

    __tablename__ = "appeals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    ban_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    fingerprint_hash: Mapped[str | None] = mapped_column(String(66), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StylometryProfile(Base):
    """Writing-style fingerprint built from channel messages."""

    __tablename__ = "stylometry"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    feature_vector: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MessageLog(Base):
    """Raw message feature snapshots for stylometry updates."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_features: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IPSession(Base):
    """IP hash sessions for pattern detection."""

    __tablename__ = "ip_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip_hash: Mapped[str] = mapped_column(String(66), index=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChannelSecuritySettings(Base):
    """Per-channel security policy configured via /security wizard or admin API."""

    __tablename__ = "channel_security_settings"

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    security_preset: Mapped[str] = mapped_column(String(16), default="balanced")
    ban_evasion_auto_deny_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    local_similarity_flag_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_registry_mode: Mapped[str] = mapped_column(String(16), default="read")
    share_bans_to_network: Mapped[bool] = mapped_column(Boolean, default=False)
    network_auto_reject_categories: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    instant_ban_categories: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    social_profiling_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    social_api_fail_mode: Mapped[str] = mapped_column(
        String(16), default="fail_open", server_default="fail_open"
    )
    social_pending_score_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    social_external_api_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    admin_ops_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    wizard_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    wizard_version: Mapped[int] = mapped_column(Integer, default=1)
