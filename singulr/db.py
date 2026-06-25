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
            "ALTER TABLE channel_security_settings ADD COLUMN IF NOT EXISTS wizard_version INTEGER DEFAULT 1",
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
    if settings_cols and "wizard_version" not in settings_cols:
        await conn.execute(
            text("ALTER TABLE channel_security_settings ADD COLUMN wizard_version INTEGER DEFAULT 1")
        )
