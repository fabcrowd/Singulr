"""Shared pytest fixtures for async SQLAlchemy tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from singulr.db import Base, get_session
from singulr import models  # noqa: F401
from singulr.services.rate_limit import reset_verify_limiter
from singulr.services.join_velocity import reset_join_velocity_tracker


@pytest.fixture(autouse=True)
def _clear_verify_rate_limiters() -> None:
    """Isolate verify rate limiter state between tests."""
    reset_verify_limiter()
    reset_join_velocity_tracker()
    yield
    reset_verify_limiter()
    reset_join_velocity_tracker()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite session with fresh schema per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def make_get_session_override(session: AsyncSession) -> Callable[[], AsyncGenerator[AsyncSession, None]]:
    """Build a FastAPI dependency override that yields the given test session."""

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return override_get_session


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """httpx client against FastAPI app with in-memory DB session."""
    from singulr.main import app

    app.dependency_overrides[get_session] = make_get_session_override(db_session)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
