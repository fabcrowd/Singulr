"""Documentation tests for social profiling operator guides."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_env_example_documents_social_vars() -> None:
    """Operators can discover social env keys from .env.example."""
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "SOCIAL_BLOCKLIST_PATH" in text
    assert "SOCIAL_API_URL" in text
    assert "SOCIAL_API_KEY" in text


def test_readme_has_social_profiling_section() -> None:
    """README explains social profiling for channel admins."""
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert "## Social profiling" in text
    assert "blocklist" in text.lower()


def test_example_blocklist_and_deploy_notes() -> None:
    """Example blocklist and deploy doc cover operator setup."""
    assert (REPO / "data" / "social_blocklist.example.json").is_file()
    deploy = (REPO / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
    assert "social" in deploy.lower()
    assert "/security" in deploy


def test_ship_report_mentions_verify() -> None:
    """Overnight ship report references the verify gate."""
    report = (REPO / "docs" / "autopilot" / "overnight-continue" / "SHIP_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert "verify.ps1" in report
    assert "social-profiling" in report
