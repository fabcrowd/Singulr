"""Generic HTTP external social profile API provider."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from singulr.services.social_profile import (
    SocialProfileContext,
    SocialProfileProviderError,
    SocialProfileResult,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 1.5


class ExternalApiProvider:
    """Call a configured social scoring HTTP API."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str = "",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._timeout = timeout_seconds

    async def analyze(self, ctx: SocialProfileContext) -> SocialProfileResult:
        """POST profile fields and map the JSON response."""
        payload = {
            "telegram_user_id": ctx.telegram_user_id,
            "username": ctx.username,
            "display_name": ctx.display_name,
            "channel_id": ctx.channel_id,
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._url, json=payload, headers=headers)
                response.raise_for_status()
                raw_body = response.text
        except httpx.HTTPError as exc:
            logger.warning("external social API error user_id=%s: %s", ctx.telegram_user_id, exc)
            raise SocialProfileProviderError("external social API failed") from exc

        try:
            data: dict[str, Any] = json.loads(raw_body)
        except ValueError as exc:
            logger.warning(
                "external social API invalid JSON user_id=%s",
                ctx.telegram_user_id,
            )
            raise SocialProfileProviderError("external social API invalid response") from exc

        try:
            hard = [str(x) for x in data.get("hard_categories") or []]
            soft = [str(x) for x in data.get("soft_signals") or []]
            score = int(data.get("risk_score") or 0)
        except (TypeError, ValueError) as exc:
            raise SocialProfileProviderError("external social API malformed payload") from exc
        summary = str(data.get("summary") or "External social API result")
        logger.info(
            "external social API user_id=%s score=%s hard=%s",
            ctx.telegram_user_id,
            score,
            ",".join(hard) or "none",
        )
        return SocialProfileResult(
            risk_score=score,
            hard_categories=hard,
            soft_signals=soft,
            summary=summary,
            sources=["external_api"],
        )
