"""Structural checks for overnight-improve research artifacts."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESEARCH = REPO / "docs" / "autopilot" / "overnight-improve" / "research.md"
IMPROVEMENT_LOG = REPO / "docs" / "autopilot" / "overnight-improve" / "improvement-log.md"
IMPROVE_REPORT = REPO / "docs" / "autopilot" / "overnight-improve" / "IMPROVE_REPORT.md"

_CANDIDATE_RE = re.compile(r"^###\s+\d+\.", re.MULTILINE)


def test_research_md_exists_with_improvement_candidates() -> None:
    """Research dossier lists at least five numbered improvement candidates."""
    assert RESEARCH.is_file()
    text = RESEARCH.read_text(encoding="utf-8")
    candidates = _CANDIDATE_RE.findall(text)
    assert len(candidates) >= 5
    assert "handlers.py" in text or "bot" in text.lower()
    assert "watcher" in text.lower() or "matching" in text.lower()


def test_improvement_log_exists() -> None:
    """Req 6 logs the shipped improvement in improvement-log.md."""
    assert IMPROVEMENT_LOG.is_file()
    text = IMPROVEMENT_LOG.read_text(encoding="utf-8")
    assert "TokenRateLimitError" in text


def test_improve_report_mentions_verify_and_requirements() -> None:
    """Final ship report documents verify.ps1 and requirement counts."""
    assert IMPROVE_REPORT.is_file()
    text = IMPROVE_REPORT.read_text(encoding="utf-8")
    assert "verify.ps1" in text
    assert "7/7" in text or "7 requirements" in text.lower() or "143" in text
