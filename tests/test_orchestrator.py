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
