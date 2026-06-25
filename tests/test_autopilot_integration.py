"""Integration smoke tests for Cursor autopilot CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PY = sys.executable


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run orchestrator CLI from repo root."""
    return subprocess.run(
        [_PY, "-m", "orchestrator", *args],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_autopilot_status_shows_active_task() -> None:
    """Status command reports the active autopilot task progress."""
    active_path = _REPO / ".autopilot" / "active.json"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    task_stem = Path(active["taskFile"]).stem

    result = _run("autopilot", "status")
    assert result.returncode == 0
    assert task_stem in result.stdout
    assert "Progress:" in result.stdout


def test_autopilot_next_writes_brief_or_done() -> None:
    """Next command creates NEXT_TASK or reports all requirements done."""
    result = _run("autopilot", "next")
    if result.returncode == 0:
        assert (_REPO / "tasks" / "NEXT_TASK.md").exists()
        assert "Assigned requirement" in result.stdout
    else:
        assert "No eligible requirements" in result.stdout


def test_autopilot_verify_req1_passes_with_ci_workflow() -> None:
    """Quick verify passes for requirement 1 of the active task file."""
    result = _run("autopilot", "verify", "1", "--quick")
    payload = json.loads(result.stdout)
    assert payload["req_id"] == "1"
    assert payload["passed"] is True
