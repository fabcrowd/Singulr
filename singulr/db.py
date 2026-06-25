"""SQLAlchemy async database setup."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from singulr.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for FastAPI dependencies."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create all tables and apply additive schema patches."""
    from singulr import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_schema_patches(conn)


async def _apply_schema_patches(conn) -> None:
    """Idempotent ALTERs for columns added after initial deploy."""
    from sqlalchemy import text

    dialect = conn.dialect.name
    if dialect == "postgresql":
        statements = [
            "ALTER TABLE bans ADD COLUMN IF NOT EXISTS chain_ban_index INTEGER DEFAULT 0",
            "ALTER TABLE bans ADD COLUMN IF NOT EXISTS status VARCHAR(16) DEFAULT 'active'",
            "ALTER TABLE bans ADD COLUMN IF NOT EXISTS overturned_at TIMESTAMPTZ",
            "ALTER TABLE channel_security_settings ADD COLUMN IF NOT EXISTS share_bans_to_network BOOLEAN DEFAULT FALSE",
            "ALTER TABLE channel_security_settings ADD COLUMN IF NOT EXISTS network_auto_reject_categories JSONB",
            "ALTER TABLE channel_security_settings ADD COLUMN IF NOT EXISTS instant_ban_categories JSONB",
            "ALTER TABLE channel_security_settings ADD COLUMN IF NOT EXISTS social_profiling_enabled BOOLEAN DEFAULT TRUE",
            "ALTER TABLE channel_security_settings ADD COLUMN IF NOT EXISTS social_api_fail_mode VARCHAR(16) DEFAULT 'fail_open'",
            "ALTER TABLE channel_security_settings ADD COLUMN IF NOT EXISTS social_pending_score_threshold INTEGER",
            "ALTER TABLE channel_security_settings ADD COLUMN IF NOT EXISTS wizard_version INTEGER DEFAULT 1",
            "ALTER TABLE tokens ADD COLUMN IF NOT EXISTS join_username VARCHAR(64)",
            "ALTER TABLE tokens ADD COLUMN IF NOT EXISTS join_display_name VARCHAR(256)",
            "ALTER TABLE tokens ADD COLUMN IF NOT EXISTS join_language_code VARCHAR(16)",
            "ALTER TABLE tokens ADD COLUMN IF NOT EXISTS join_channel_title VARCHAR(256)",
            "ALTER TABLE tokens ADD COLUMN IF NOT EXISTS social_profile_cache JSONB",
            "ALTER TABLE tokens ADD COLUMN IF NOT EXISTS social_analyzed_at TIMESTAMPTZ",
        ]
        for statement in statements:
            await conn.execute(text(statement))
        return

    if dialect != "sqlite":
        return

    async def _sqlite_columns(table: str) -> set[str]:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in result.fetchall()}

    ban_cols = await _sqlite_columns("bans")
    if "chain_ban_index" not in ban_cols:
        await conn.execute(text("ALTER TABLE bans ADD COLUMN chain_ban_index INTEGER DEFAULT 0"))
    if "status" not in ban_cols:
        await conn.execute(text("ALTER TABLE bans ADD COLUMN status VARCHAR(16) DEFAULT 'active'"))
    if "overturned_at" not in ban_cols:
        await conn.execute(text("ALTER TABLE bans ADD COLUMN overturned_at DATETIME"))

    settings_cols = await _sqlite_columns("channel_security_settings")
    if settings_cols and "share_bans_to_network" not in settings_cols:
        await conn.execute(
            text("ALTER TABLE channel_security_settings ADD COLUMN share_bans_to_network BOOLEAN DEFAULT 0")
        )
    if settings_cols and "network_auto_reject_categories" not in settings_cols:
        await conn.execute(
            text("ALTER TABLE channel_security_settings ADD COLUMN network_auto_reject_categories JSON")
        )
    if settings_cols and "instant_ban_categories" not in settings_cols:
        await conn.execute(
            text("ALTER TABLE channel_security_settings ADD COLUMN instant_ban_categories JSON")
        )
    if settings_cols and "social_profiling_enabled" not in settings_cols:
        await conn.execute(
            text(
                "ALTER TABLE channel_security_settings ADD COLUMN social_profiling_enabled BOOLEAN DEFAULT 1"
            )
        )
    if settings_cols and "social_api_fail_mode" not in settings_cols:
        await conn.execute(
            text(
                "ALTER TABLE channel_security_settings ADD COLUMN social_api_fail_mode VARCHAR(16) DEFAULT 'fail_open'"
            )
        )
    if settings_cols and "social_pending_score_threshold" not in settings_cols:
        await conn.execute(
            text(
                "ALTER TABLE channel_security_settings ADD COLUMN social_pending_score_threshold INTEGER"
            )
        )
    if settings_cols and "wizard_version" not in settings_cols:
        await conn.execute(
            text("ALTER TABLE channel_security_settings ADD COLUMN wizard_version INTEGER DEFAULT 1")
        )

    token_cols = await _sqlite_columns("tokens")
    if token_cols and "join_username" not in token_cols:
        await conn.execute(text("ALTER TABLE tokens ADD COLUMN join_username VARCHAR(64)"))
    if token_cols and "join_display_name" not in token_cols:
        await conn.execute(text("ALTER TABLE tokens ADD COLUMN join_display_name VARCHAR(256)"))
    if token_cols and "join_language_code" not in token_cols:
        await conn.execute(text("ALTER TABLE tokens ADD COLUMN join_language_code VARCHAR(16)"))
    if token_cols and "join_channel_title" not in token_cols:
        await conn.execute(text("ALTER TABLE tokens ADD COLUMN join_channel_title VARCHAR(256)"))
    if token_cols and "social_profile_cache" not in token_cols:
        await conn.execute(text("ALTER TABLE tokens ADD COLUMN social_profile_cache JSON"))
    if token_cols and "social_analyzed_at" not in token_cols:
        await conn.execute(text("ALTER TABLE tokens ADD COLUMN social_analyzed_at DATETIME"))
