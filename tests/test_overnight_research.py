"""Structural checks for overnight-improve research artifacts."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESEARCH = REPO / "docs" / "autopilot" / "overnight-improve" / "research.md"

_CANDIDATE_RE = re.compile(r"^###\s+\d+\.", re.MULTILINE)


def test_research_md_exists_with_improvement_candidates() -> None:
    """Research dossier lists at least five numbered improvement candidates."""
    assert RESEARCH.is_file()
    text = RESEARCH.read_text(encoding="utf-8")
    candidates = _CANDIDATE_RE.findall(text)
    assert len(candidates) >= 5
    assert "handlers.py" in text or "bot" in text.lower()
    assert "watcher" in text.lower() or "matching" in text.lower()
