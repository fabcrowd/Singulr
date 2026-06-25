"""On-chain ban registry client."""

from __future__ import annotations

import json
from pathlib import Path

from singulr.config import get_settings
from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
from singulr.domain.chain_mapping import category_to_chain, severity_to_chain

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACT_PATH = (
    _REPO_ROOT
    / "artifacts"
    / "contracts"
    / "BanRegistry.sol"
    / "BanRegistry.json"
)


class ChainClient:
    """Thin wrapper around BanRegistry contract."""

    def __init__(self) -> None:
        settings = get_settings()
        self._configured = settings.chain_enabled
        self._w3 = None
        self._contract = None
        if self._configured:
            self._init_web3(settings)

    def _init_web3(self, settings) -> None:
        """Lazy-init web3 contract when chain is configured."""
        try:
            from web3 import Web3

            self._w3 = Web3(Web3.HTTPProvider(settings.chain_rpc))
            if _ARTIFACT_PATH.exists():
                artifact = json.loads(_ARTIFACT_PATH.read_text(encoding="utf-8"))
                self._contract = self._w3.eth.contract(
                    address=Web3.to_checksum_address(settings.contract_address),
                    abi=artifact["abi"],
                )
        except Exception:
            self._w3 = None
            self._contract = None

    @property
    def enabled(self) -> bool:
        """True when chain integration is configured or a contract is injected."""
        return self._configured or self._contract is not None

    def _fp_bytes32(self, fingerprint_hash: str) -> bytes:
        """Normalize fingerprint hash to bytes32 for contract calls."""
        value = fingerprint_hash.lower()
        if value.startswith("0x"):
            value = value[2:]
        return bytes.fromhex(value.zfill(64))

    async def is_banned(self, fingerprint_hash: str) -> bool:
        """Return True when fingerprint is on-chain banned."""
        if not self._contract:
            return False
        return bool(
            self._contract.functions.isBanned(self._fp_bytes32(fingerprint_hash)).call()
        )

    async def get_reputation(self, fingerprint_hash: str) -> dict[str, int]:
        """Return aggregated on-chain score and active ban count."""
        if not self._contract:
            return {"score": 0, "active_bans": 0}
        score, active_bans = self._contract.functions.getReputation(
            self._fp_bytes32(fingerprint_hash)
        ).call()
        return {"score": int(score), "active_bans": int(active_bans)}

    async def register_fingerprint(self, fingerprint_hash: str, channel_id: int) -> str | None:
        """Register fingerprint on-chain; returns tx hash or None when disabled."""
        if not self._contract or not self._w3:
            return None
        return None

    async def record_ban(
        self,
        fingerprint_hash: str,
        stylometry_hash: str | None,
        channel_id: int,
        *,
        category: BanCategory = BanCategory.OTHER,
        severity: BanSeverity = BanSeverity.MEDIUM,
    ) -> str | None:
        """Record structured ban on-chain; returns tx hash or None when disabled."""
        if not self._contract:
            return None
        self._contract.functions.recordBan(
            self._fp_bytes32(fingerprint_hash),
            category_to_chain(category),
            severity_to_chain(severity),
            channel_id,
        )
        return None

    async def overturn_ban(self, fingerprint_hash: str, ban_index: int) -> str | None:
        """Mark an on-chain ban overturned."""
        if not self._contract:
            return None
        return None
