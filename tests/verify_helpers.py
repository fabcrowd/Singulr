"""Shared helpers for verify API tests."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from singulr.services.tokens import validate_token
from singulr.services.verify_session import (
    compute_challenge_proof,
    issue_challenge_secret,
)


async def challenge_proof_for(
    client: httpx.AsyncClient,
    token: str,
    *,
    visitor_id: str = "visitor-api-test",
    session: AsyncSession | None = None,
    bound_visitor_id: str | None = None,
) -> str:
    """Return HMAC challenge proof for verify submit tests.

    When ``session`` is provided, bind a fresh secret on the token row without
    calling precheck (use when ``check_known_bad`` is mocked).
    """
    if session is not None:
        secret = issue_challenge_secret()
        token_row = await validate_token(session, token)
        assert token_row is not None
        token_row.verify_challenge_secret = secret
        token_row.bound_visitor_id = (
            bound_visitor_id if bound_visitor_id is not None else visitor_id
        )
        await session.commit()
        return compute_challenge_proof(secret, token=token, visitor_id=visitor_id)

    pre = await client.post(
        "/api/verify/precheck",
        json={"token": token, "visitor_id": visitor_id},
    )
    assert pre.status_code == 200, pre.text
    secret = pre.json()["challenge_secret"]
    return compute_challenge_proof(secret, token=token, visitor_id=visitor_id)
