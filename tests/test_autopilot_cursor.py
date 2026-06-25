"""Tests for Cursor-native autopilot bridge."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.autopilot_cursor import (
    load_task_file,
    pick_next_requirement,
    set_active_task,
    verify_requirement,
)

_REPO = Path(__file__).resolve().parents[1]
_TASK_FILE = _REPO / "docs/autopilot/production-hardening/production-hardening.json"


def test_pick_next_respects_dependencies() -> None:
    """Next eligible requirement has satisfied dependencies (or none left)."""
    task = load_task_file(_TASK_FILE)
    nxt = pick_next_requirement(task)
    if nxt is None:
        assert all(r.passes or r.stuck for r in task.requirements)
        return
    for dep_id in nxt.depends_on:
        dep = task.requirement(dep_id)
        assert dep is not None and dep.passes


def test_active_task_roundtrip(tmp_path: Path, monkeypatch) -> None:
    """set_active_task writes path readable by load_task_file."""
    sample = tmp_path / "sample.json"
    sample.write_text(
        json.dumps(
            {
                "name": "x",
                "requirements": [
                    {
                        "id": "1",
                        "description": "do thing",
                        "acceptance": ["README.md exists"],
                        "passes": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    from orchestrator import autopilot_cursor as mod

    active = tmp_path / "active.json"
    monkeypatch.setattr(mod, "ACTIVE_PATH", active)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    set_active_task(sample)
    loaded = load_task_file()
    assert loaded.name == "x"


def test_verify_unknown_requirement(monkeypatch) -> None:
    """Unknown id fails verification."""
    from orchestrator import autopilot_cursor as mod

    monkeypatch.setattr(mod, "ACTIVE_PATH", _REPO / ".autopilot" / "active.json")
    monkeypatch.setattr(mod, "REPO_ROOT", _REPO)
    report = verify_requirement("999", full_suite=False)
    assert not report.passed
