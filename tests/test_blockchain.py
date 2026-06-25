"""Tests for on-chain ban registry client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from singulr.config import Settings
from singulr.services.blockchain import ChainClient


def test_chain_client_disabled_without_contract_address() -> None:
    """Chain is off when contract address is not configured."""
    settings = Settings(contract_address="", wallet_private_key="")

    with patch("singulr.services.blockchain.get_settings", return_value=settings):
        client = ChainClient()

    assert client.enabled is False


@pytest.mark.asyncio
async def test_is_banned_returns_true_when_contract_says_so() -> None:
    """Injected contract isBanned True propagates to ChainClient."""
    fingerprint = "0x" + "ab" * 32
    settings = Settings(
        contract_address="0x1234567890123456789012345678901234567890",
        wallet_private_key="0x" + "1" * 64,
    )

    mock_contract = MagicMock()
    mock_contract.functions.isBanned.return_value.call.return_value = True

    with patch("singulr.services.blockchain.get_settings", return_value=settings):
        client = ChainClient()
        client._contract = mock_contract
        banned = await client.is_banned(fingerprint)

    assert banned is True
    mock_contract.functions.isBanned.assert_called_once()


@pytest.mark.asyncio
async def test_record_ban_skipped_when_chain_disabled() -> None:
    """record_ban is a no-op when chain integration is not configured."""
    settings = Settings(contract_address="", wallet_private_key="")

    with patch("singulr.services.blockchain.get_settings", return_value=settings):
        client = ChainClient()
        tx_hash = await client.record_ban("0x" + "cd" * 32, None, 42)

    assert client.enabled is False
    assert tx_hash is None
