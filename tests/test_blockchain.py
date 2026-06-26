"""Tests for on-chain ban registry client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from singulr.config import Settings
from singulr.domain.ban_taxonomy import BanCategory, BanSeverity
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
async def test_get_reputation_returns_score_and_active_bans() -> None:
    """get_reputation maps contract tuple to score and active_bans."""
    fingerprint = "0x" + "ef" * 32
    settings = Settings(
        contract_address="0x1234567890123456789012345678901234567890",
        wallet_private_key="0x" + "2" * 64,
    )
    mock_contract = MagicMock()
    mock_contract.functions.getReputation.return_value.call.return_value = (150, 2)

    with patch("singulr.services.blockchain.get_settings", return_value=settings):
        client = ChainClient()
        client._contract = mock_contract
        result = await client.get_reputation(fingerprint)

    assert result == {"score": 150, "active_bans": 2}
    mock_contract.functions.getReputation.assert_called_once()


@pytest.mark.asyncio
async def test_record_ban_passes_category_and_severity_to_contract() -> None:
    """record_ban forwards taxonomy ordinals to the chain client."""
    settings = Settings(
        contract_address="0x1234567890123456789012345678901234567890",
        wallet_private_key="0x" + "3" * 64,
    )
    mock_contract = MagicMock()
    record_fn = MagicMock()
    mock_contract.functions.recordBan.return_value = record_fn

    with patch("singulr.services.blockchain.get_settings", return_value=settings):
        client = ChainClient()
        client._contract = mock_contract
        await client.record_ban(
            "0x" + "11" * 32,
            None,
            42,
            category=BanCategory.SCAM_FRAUD,
            severity=BanSeverity.PERMANENT,
        )

    mock_contract.functions.recordBan.assert_called_once()


@pytest.mark.asyncio
async def test_record_ban_skipped_when_chain_disabled() -> None:
    """record_ban is a no-op when chain integration is not configured."""
    settings = Settings(contract_address="", wallet_private_key="")

    with patch("singulr.services.blockchain.get_settings", return_value=settings):
        client = ChainClient()
        tx_hash = await client.record_ban("0x" + "cd" * 32, None, 42)

    assert client.enabled is False
    assert tx_hash is None


def test_chain_client_survives_web3_init_failure() -> None:
    """RPC or artifact init errors leave chain reads unavailable (fail-open reads)."""
    settings = Settings(
        contract_address="0x1234567890123456789012345678901234567890",
        wallet_private_key="0x" + "4" * 64,
    )

    with patch("singulr.services.blockchain.get_settings", return_value=settings):
        with patch("web3.Web3", side_effect=OSError("rpc down")):
            client = ChainClient()

    assert client._contract is None


@pytest.mark.asyncio
async def test_is_banned_fail_open_when_contract_unavailable_after_init_error() -> None:
    """is_banned returns False when chain client could not initialize."""
    settings = Settings(
        contract_address="0x1234567890123456789012345678901234567890",
        wallet_private_key="0x" + "5" * 64,
    )

    with patch("singulr.services.blockchain.get_settings", return_value=settings):
        with patch("web3.Web3", side_effect=OSError("rpc down")):
            client = ChainClient()
            banned = await client.is_banned("0x" + "fe" * 32)

    assert banned is False
