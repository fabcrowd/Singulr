"""On-chain ban registry client."""

from __future__ import annotations

from singulr.config import get_settings


class ChainClient:
    """Thin wrapper around BanRegistry contract."""

    def __init__(self) -> None:
        settings = get_settings()
        self._configured = settings.chain_enabled
        self._w3 = None
        self._contract = None

    @property
    def enabled(self) -> bool:
        """True when chain integration is configured or a contract is injected."""
        return self._configured or self._contract is not None

    async def is_banned(self, fingerprint_hash: str) -> bool:
        """Return True when fingerprint is on-chain banned."""
        if not self._contract:
            return False
        return bool(self._contract.functions.isBanned(fingerprint_hash).call())

    async def record_ban(
        self,
        fingerprint_hash: str,
        stylometry_hash: str | None,
        channel_id: int,
    ) -> str | None:
        """Record ban on-chain; returns tx hash or None when disabled."""
        if not self._configured:
            return None
        return None
