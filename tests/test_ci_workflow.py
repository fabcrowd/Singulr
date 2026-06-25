"""Structural checks for GitHub Actions CI workflow."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CI_PATH = REPO / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_file_exists() -> None:
    """CI workflow is present."""
    assert CI_PATH.is_file()


def test_ci_workflow_runs_pytest_ruff_and_compile() -> None:
    """Workflow mirrors local verify suite."""
    text = CI_PATH.read_text(encoding="utf-8").lower()
    assert "pytest" in text
    assert "ruff" in text
    assert "compile" in text or "hardhat" in text


def test_ci_workflow_uses_python_and_node() -> None:
    """Toolchain versions are pinned for CI."""
    text = CI_PATH.read_text(encoding="utf-8")
    assert "python-version" in text
    assert "'3.12" in text or '"3.12' in text or "3.11" in text
    assert "node-version" in text
    assert "'20" in text or '"20' in text


def test_ci_workflow_triggers_on_push_and_pr() -> None:
    """Workflow runs on push and pull_request."""
    text = CI_PATH.read_text(encoding="utf-8")
    assert "push:" in text
    assert "pull_request:" in text
