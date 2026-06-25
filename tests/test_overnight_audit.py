"""Structural checks for overnight-improve audit artifact."""

from __future__ import annotations

from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1] / "docs" / "autopilot" / "overnight-improve" / "audit.md"


def test_audit_md_has_severity_sections() -> None:
    """Bug audit documents severity-labelled findings."""
    assert AUDIT.is_file()
    text = AUDIT.read_text(encoding="utf-8").lower()
    assert "critical" in text
    assert "finding" in text or "bug" in text
