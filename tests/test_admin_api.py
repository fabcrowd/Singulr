"""Admin API tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.models import AppealRecord, Ban
from singulr.services.reinstatement import BAN_STATUS_ACTIVE, BAN_STATUS_OVERTURNED


@pytest.mark.asyncio
async def test_admin_routes_return_503_when_api_key_unset(api_client: httpx.AsyncClient) -> None:
    """Admin routes are disabled when ADMIN_API_KEY is not configured."""
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("ADMIN_API_KEY", raising=False)
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.get("/api/admin/bans")

    assert response.status_code == 503
    assert response.json()["detail"] == "admin_api_disabled"


@pytest.mark.asyncio
async def test_admin_bans_requires_api_key(api_client: httpx.AsyncClient) -> None:
    """GET /api/admin/bans without key returns 401."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.get("/api/admin/bans")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_bans_lists_records_with_valid_key(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/admin/bans with X-Admin-Key returns ban list."""
    db_session.add(
        Ban(
            telegram_user_id=12345,
            fingerprint_hash="0x" + "b" * 64,
            reason="spam",
        )
    )
    await db_session.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.get(
            "/api/admin/bans",
            headers={"X-Admin-Key": "secret-admin-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["telegram_user_id"] == 12345
    assert body[0]["reason"] == "spam"
    assert "fingerprint_hash" in body[0]


@pytest.mark.asyncio
async def test_admin_unban_requires_api_key(api_client: httpx.AsyncClient) -> None:
    """POST /api/admin/unban without key returns 401."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.post("/api/admin/unban", json={"ban_id": 1})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_unban_requires_ban_id_or_user_id(api_client: httpx.AsyncClient) -> None:
    """POST /api/admin/unban without identifiers returns 400."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.post(
            "/api/admin/unban",
            json={},
            headers={"X-Admin-Key": "secret-admin-key"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "ban_id_or_telegram_user_id_required"


@pytest.mark.asyncio
async def test_admin_unban_returns_404_when_no_active_ban(api_client: httpx.AsyncClient) -> None:
    """POST /api/admin/unban returns 404 when no active ban matches."""
    chain = MagicMock()
    chain.overturn_ban = AsyncMock(return_value="0xbeef")

    with patch("singulr.api.admin._chain", chain):
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("ADMIN_API_KEY", "secret-admin-key")
            from singulr.config import get_settings

            get_settings.cache_clear()
            response = await api_client.post(
                "/api/admin/unban",
                json={"telegram_user_id": 99999},
                headers={"X-Admin-Key": "secret-admin-key"},
            )

    assert response.status_code == 404
    assert response.json()["detail"] == "active_ban_not_found"


@pytest.mark.asyncio
async def test_admin_unban_overturns_active_ban(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /api/admin/unban overturns an active ban by ban_id."""
    ban = Ban(
        telegram_user_id=55001,
        fingerprint_hash="0x" + "c" * 64,
        reason="appeal granted",
        status=BAN_STATUS_ACTIVE,
    )
    db_session.add(ban)
    await db_session.commit()

    chain = MagicMock()
    chain.overturn_ban = AsyncMock(return_value="0xbeef")

    with patch("singulr.api.admin._chain", chain):
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("ADMIN_API_KEY", "secret-admin-key")
            from singulr.config import get_settings

            get_settings.cache_clear()
            response = await api_client.post(
                "/api/admin/unban",
                json={"ban_id": ban.id},
                headers={"X-Admin-Key": "secret-admin-key"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ban_id"] == ban.id
    assert body["status"] == BAN_STATUS_OVERTURNED


@pytest.mark.asyncio
async def test_admin_appeals_list_requires_api_key(api_client: httpx.AsyncClient) -> None:
    """GET /api/admin/appeals without key returns 401."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.get("/api/admin/appeals")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_appeals_lists_records_with_valid_key(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/admin/appeals with X-Admin-Key returns appeal list."""
    db_session.add(
        AppealRecord(
            telegram_user_id=66001,
            reason="false positive",
            status="pending",
        )
    )
    await db_session.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADMIN_API_KEY", "secret-admin-key")
        from singulr.config import get_settings

        get_settings.cache_clear()
        response = await api_client.get(
            "/api/admin/appeals",
            headers={"X-Admin-Key": "secret-admin-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["telegram_user_id"] == 66001
    assert body[0]["reason"] == "false positive"
    assert body[0]["status"] == "pending"
