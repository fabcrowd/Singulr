"""ORM models for profiles, bans, tokens, and messages."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from singulr.db import Base


class VerificationToken(Base):
    """One-time token tying a Telegram user to a verification session."""

    __tablename__ = "tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


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
    banned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    chain_tx: Mapped[str | None] = mapped_column(String(80), nullable=True)


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
