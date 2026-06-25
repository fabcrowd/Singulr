"""Structural checks for deployment runbook."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY_DOC = REPO / "docs" / "DEPLOY.md"


def test_deploy_doc_exists() -> None:
    """Deployment runbook is present."""
    assert DEPLOY_DOC.is_file()


def test_deploy_doc_has_numbered_steps() -> None:
    """Runbook includes at least twelve numbered steps."""
    text = DEPLOY_DOC.read_text(encoding="utf-8")
    numbered = re.findall(r"^\s*\d+\.\s+", text, flags=re.MULTILINE)
    assert len(numbered) >= 12


def test_deploy_doc_covers_compose_admin_and_health() -> None:
    """Runbook documents compose prod, admin key, and health checks."""
    text = DEPLOY_DOC.read_text(encoding="utf-8").lower()
    assert "docker compose" in text
    assert "docker-compose.prod.yml" in text
    assert "admin_api_key" in text
    assert "/health" in text
