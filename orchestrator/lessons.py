"""Failure memory and golden packets."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.prd import LESSONS_PATH, RUNS_DIR, Task
from orchestrator.verifier import VerifyReport

LESSON_HEADER = """
### {date} — {task_id} — {title}
- **Symptom:** {symptom}
- **Root cause:** {root_cause}
- **Fix:** (agent to fill on retry)
- **Guard:** re-run `python -m orchestrator verify {task_id}`

"""


def append_lesson(task: Task, symptom: str, root_cause: str) -> None:
    """Append a lesson block to tasks/lessons.md."""
    block = LESSON_HEADER.format(
        date=datetime.now(UTC).strftime("%Y-%m-%d"),
        task_id=task.id,
        title=task.title,
        symptom=symptom,
        root_cause=root_cause,
    )
    existing = LESSONS_PATH.read_text(encoding="utf-8") if LESSONS_PATH.exists() else ""
    LESSONS_PATH.write_text(existing.rstrip() + "\n" + block, encoding="utf-8")


def write_golden_packet(
    task: Task,
    *,
    reason: str,
    report: VerifyReport | None = None,
    extra: dict | None = None,
) -> Path:
    """Persist failure context for the next agent attempt."""
    run_dir = RUNS_DIR / task.id
    run_dir.mkdir(parents=True, exist_ok=True)
    packet = {
        "task_id": task.id,
        "title": task.title,
        "timestamp": datetime.now(UTC).isoformat(),
        "reason": reason,
        "failed_checks": [
            {"name": c.name, "detail": c.detail} for c in (report.failed_checks() if report else [])
        ],
        "extra": extra or {},
    }
    path = run_dir / "failure.json"
    path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    return path


def recent_lessons(max_chars: int = 2500) -> str:
    """Return tail of lessons file for session injection."""
    if not LESSONS_PATH.exists():
        return ""
    text = LESSONS_PATH.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return "...(truncated)\n" + text[-max_chars:]


def load_golden_packet(task_id: str) -> dict | None:
    """Load latest failure packet for a task if present."""
    path = RUNS_DIR / task_id / "failure.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
