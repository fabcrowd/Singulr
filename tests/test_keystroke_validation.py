"""Tests for keystroke plausibility validation."""

from __future__ import annotations

from singulr.services.keystroke_validation import (
    MAX_KEYSTROKES,
    is_synthetic_keystroke_rhythm,
    is_too_fast_typing,
    keystroke_risk_factors,
    submit_body_too_large,
)


def _uniform_keystrokes(count: int = 20, flight: float = 50.0) -> list[dict]:
    return [
      {"key": "a", "down": i * flight, "up": i * flight + 40, "flight": flight}
      for i in range(count)
  ]


def _fast_keystrokes(count: int = 20) -> list[dict]:
    return [
        {"key": "a", "down": i * 10, "up": i * 10 + 8, "flight": 10}
        for i in range(count)
    ]


def test_is_synthetic_keystroke_rhythm_detects_uniform_flights() -> None:
    """Flat flight times are treated as synthetic."""
    assert is_synthetic_keystroke_rhythm(_uniform_keystrokes()) is True


def test_is_synthetic_keystroke_rhythm_allows_human_like_variance() -> None:
    """Natural timing variance is not flagged."""
    varied = [
        {"key": "a", "down": 0, "up": 70, "flight": 0},
        {"key": "b", "down": 120, "up": 180, "flight": 50},
        {"key": "c", "down": 260, "up": 320, "flight": 80},
        {"key": "d", "down": 500, "up": 560, "flight": 180},
        {"key": "e", "down": 700, "up": 760, "flight": 140},
    ]
    assert is_synthetic_keystroke_rhythm(varied) is False


def test_is_too_fast_typing_detects_short_sessions() -> None:
    """Very short sessions are flagged as too fast."""
    assert is_too_fast_typing(_fast_keystrokes()) is True


def test_keystroke_risk_factors_include_synthetic_and_fast_labels() -> None:
    """Risk factor labels cover synthetic rhythm and speed."""
    factors = keystroke_risk_factors(_fast_keystrokes())
    assert "too_fast_verify" in factors
    assert "synthetic_keystroke" in factors


def test_submit_body_too_large_rejects_huge_payload() -> None:
    """Oversized serialized submit bodies are rejected."""
    payload = {
        "token": "t",
        "visitor_id": "v",
        "typed_text": "x" * 70_000,
        "keystrokes": [],
    }
    assert submit_body_too_large(payload) is True


def test_max_keystrokes_constant_documents_submit_cap() -> None:
    """Submit keystroke cap matches pydantic Field max_length."""
    assert MAX_KEYSTROKES == 500
