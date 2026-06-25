"""Tests for Conductor orchestrator."""

from __future__ import annotations

from orchestrator.prd import load_tasks, pick_next_task, pick_parallel_batch
from orchestrator.verifier import check_structural_criterion


def test_prd_loads_tasks() -> None:
    """PRD contains expected task count."""
    tasks = load_tasks()
    assert len(tasks) >= 18
    assert any(t.id == "T001" for t in tasks)


def test_pick_next_returns_lowest_pending() -> None:
    """Next task is lowest id with satisfied deps among pending work."""
    tasks = load_tasks()
    pending = [t for t in tasks if t.status == "pending"]
    if not pending:
        assert pick_next_task() is None
        return
    in_progress = {t.id for t in tasks if t.status == "in_progress"}
    task = pick_next_task()
    if in_progress:
        assert task is None or task.id not in in_progress
        return
    assert task is not None
    pending_ids = sorted(t.id for t in pending)
    assert task.id == pending_ids[0]


def test_parallel_batch_respects_lane_limit() -> None:
    """Parallel batch uses different lanes."""
    tasks = load_tasks()
    if not any(t.status == "pending" for t in tasks):
        return
    batch = pick_parallel_batch(4)
    assert len(batch) >= 1
    phases = {t.phase for t in batch}
    assert len(phases) == len(batch) or len(batch) <= 4


def test_structural_file_exists_check() -> None:
    """Parser detects missing test file."""
    result = check_structural_criterion("tests/nonexistent_file_xyz.py exists")
    assert not result.passed


def test_structural_exists_in_prose_not_treated_as_file_path() -> None:
    """Sentences ending in 'exists' are not misread as file-exists criteria."""
    result = check_structural_criterion(
        "get_effective_channel_policy(session, channel_id) returns defaults from config when no row exists"
    )
    assert result.passed


def test_agent_runtime_defaults_to_cursor(tmp_path, monkeypatch) -> None:
    """Missing runtime.json defaults to cursor."""
    from orchestrator import runtime as rt

    monkeypatch.setattr(rt, "RUNTIME_PATH", tmp_path / "missing.json")
    assert rt.get_agent_runtime() == "cursor"
    assert rt.runtime_label() == "Cursor"


def test_agent_runtime_roundtrip(tmp_path, monkeypatch) -> None:
    """set_agent_runtime persists and get_agent_runtime reads back."""
    from orchestrator import runtime as rt

    path = tmp_path / "runtime.json"
    monkeypatch.setattr(rt, "RUNTIME_PATH", path)
    rt.set_agent_runtime("claude-code")
    assert rt.get_agent_runtime() == "claude-code"
    assert rt.runtime_label() == "Claude Code"
    rt.set_agent_runtime("cursor")
    assert rt.get_agent_runtime() == "cursor"


def test_agent_runtime_rejects_invalid(tmp_path, monkeypatch) -> None:
    """Invalid runtime name raises ValueError."""
    from orchestrator import runtime as rt

    monkeypatch.setattr(rt, "RUNTIME_PATH", tmp_path / "runtime.json")
    try:
        rt.set_agent_runtime("vscode")
    except ValueError as exc:
        assert "claude-code" in str(exc)
    else:
        raise AssertionError("expected ValueError")
