"""Unit tests for structured admin log channel message bodies."""

from __future__ import annotations

from singulr.services.telegram_actions import (
    _build_log_body,
    format_ban_evasion_body,
    format_elevated_risk_body,
    format_watcher_match_body,
    truncate_fingerprint_hash,
)

_SAMPLE_FINGERPRINT = "0x" + "ab" * 32


def test_truncate_fingerprint_hash_short_value_unchanged() -> None:
    """Short hashes are not truncated."""
    short = "0xabc123"
    assert truncate_fingerprint_hash(short) == short


def test_truncate_fingerprint_hash_long_value() -> None:
    """Long hashes show an 18-character prefix with ellipsis."""
    assert truncate_fingerprint_hash(_SAMPLE_FINGERPRINT) == f"{_SAMPLE_FINGERPRINT[:18]}..."


def test_format_elevated_risk_includes_user_factors_and_score() -> None:
    """Elevated-risk logs include user id, humanized signals, and parsed similarity score."""
    body = format_elevated_risk_body(
        user_id=424242,
        reason="Elevated risk - review recommended",
        risk_factors=["ip_hash_match", "keystroke_similarity:0.87"],
    )
    assert "User ID: 424242" in body
    assert "Reason: Elevated risk - review recommended" in body
    assert "Signals:" in body
    assert "Typing rhythm similarity to banned user: 87%" in body
    assert "Risk score: 87%" in body


def test_format_ban_evasion_includes_truncated_fingerprint() -> None:
    """Ban-evasion logs include user id, reason, and truncated fingerprint."""
    body = format_ban_evasion_body(
        user_id=999,
        reason="Known banned device fingerprint",
        fingerprint_hash=_SAMPLE_FINGERPRINT,
    )
    assert "User ID: 999" in body
    assert "Reason: Known banned device fingerprint" in body
    assert f"Fingerprint: {_SAMPLE_FINGERPRINT[:18]}..." in body


def test_format_watcher_match_includes_score_and_ban_fingerprint() -> None:
    """Watcher match logs include user id, score, reason, and ban fingerprint."""
    body = format_watcher_match_body(
        user_id=555,
        score=0.91,
        reason="stylometry_match",
        ban_fingerprint=_SAMPLE_FINGERPRINT,
    )
    assert "User ID: 555" in body
    assert "Match score: 91%" in body
    assert "Reason: stylometry_match" in body
    assert f"Ban fingerprint: {_SAMPLE_FINGERPRINT[:18]}..." in body


def test_build_log_body_routes_structured_event_types() -> None:
    """log_to_channel body builder selects the correct formatter per event."""
    elevated = _build_log_body(
        "ELEVATED_RISK",
        body=None,
        user_id=1,
        reason="hold",
        risk_factors=["ip_velocity"],
        fingerprint_hash=None,
        match_score=None,
        ban_fingerprint=None,
    )
    assert "User ID: 1" in elevated
    assert "Signals:" in elevated

    evasion = _build_log_body(
        "BAN_EVASION",
        body=None,
        user_id=2,
        reason="Known banned device fingerprint",
        risk_factors=None,
        fingerprint_hash=_SAMPLE_FINGERPRINT,
        match_score=None,
        ban_fingerprint=None,
    )
    assert "Fingerprint:" in evasion

    watcher = _build_log_body(
        "WATCHER_MATCH",
        body=None,
        user_id=3,
        reason="stylometry_match",
        risk_factors=None,
        fingerprint_hash=None,
        match_score=0.8,
        ban_fingerprint=_SAMPLE_FINGERPRINT,
    )
    assert "Match score: 80%" in watcher
