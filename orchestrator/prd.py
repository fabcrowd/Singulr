"""Load and mutate tasks/prd.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PRD_PATH = REPO_ROOT / "tasks" / "prd.json"
LANES_PATH = REPO_ROOT / "tasks" / "lanes.json"
LESSONS_PATH = REPO_ROOT / "tasks" / "lessons.md"
NEXT_TASK_PATH = REPO_ROOT / "tasks" / "NEXT_TASK.md"
BRIEFS_DIR = REPO_ROOT / "orchestrator" / "briefs"
RUNS_DIR = REPO_ROOT / "orchestrator" / "runs"


@dataclass
class Task:
    """Single PRD task."""

    id: str
    phase: str
    title: str
    description: str
    acceptance_criteria: list[str]
    verification: str
    status: str
    depends_on: list[str]
    notes: str | None = None
    lane: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """Build Task from PRD JSON object."""
        return cls(
            id=data["id"],
            phase=data.get("phase", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            acceptance_criteria=list(data.get("acceptance_criteria", [])),
            verification=data.get("verification", ""),
            status=data.get("status", "pending"),
            depends_on=list(data.get("depends_on", [])),
            notes=data.get("notes"),
            lane=data.get("lane"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to PRD JSON shape."""
        out: dict[str, Any] = {
            "id": self.id,
            "phase": self.phase,
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "verification": self.verification,
            "status": self.status,
        }
        if self.depends_on:
            out["depends_on"] = self.depends_on
        if self.notes:
            out["notes"] = self.notes
        if self.lane:
            out["lane"] = self.lane
        return out


def load_prd() -> dict[str, Any]:
    """Read full PRD document."""
    return json.loads(PRD_PATH.read_text(encoding="utf-8"))


def save_prd(doc: dict[str, Any]) -> None:
    """Write PRD document."""
    PRD_PATH.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def load_tasks() -> list[Task]:
    """Return all tasks from PRD."""
    doc = load_prd()
    return [Task.from_dict(t) for t in doc.get("tasks", [])]


def save_tasks(tasks: list[Task]) -> None:
    """Persist task list into PRD."""
    doc = load_prd()
    doc["tasks"] = [t.to_dict() for t in tasks]
    save_prd(doc)


def get_task(task_id: str) -> Task | None:
    """Find task by id."""
    for task in load_tasks():
        if task.id == task_id:
            return task
    return None


def update_task_status(task_id: str, status: str, notes: str | None = None) -> Task:
    """Update one task's status."""
    tasks = load_tasks()
    found: Task | None = None
    for i, task in enumerate(tasks):
        if task.id == task_id:
            task.status = status
            if notes is not None:
                task.notes = notes
            tasks[i] = task
            found = task
            break
    if not found:
        raise ValueError(f"Unknown task: {task_id}")
    save_tasks(tasks)
    return found


def load_lanes() -> dict[str, Any]:
    """Read lanes configuration."""
    return json.loads(LANES_PATH.read_text(encoding="utf-8"))


def lane_for_phase(phase: str) -> str:
    """Map PRD phase to orchestrator lane."""
    lanes_doc = load_lanes()
    for lane_name, lane in lanes_doc.get("lanes", {}).items():
        if phase in lane.get("phases", []):
            return lane_name
    return phase


def dependencies_met(task: Task, tasks: list[Task]) -> bool:
    """True when all depends_on tasks are done."""
    if not task.depends_on:
        return True
    done_ids = {t.id for t in tasks if t.status == "done"}
    return all(dep in done_ids for dep in task.depends_on)


def pick_next_task(lane: str | None = None) -> Task | None:
    """Select lowest-id pending task with satisfied dependencies."""
    tasks = load_tasks()
    in_progress_lanes = {
        lane_for_phase(t.phase) for t in tasks if t.status == "in_progress"
    }
    candidates: list[Task] = []
    for task in tasks:
        if task.status != "pending":
            continue
        if not dependencies_met(task, tasks):
            continue
        task_lane = lane_for_phase(task.phase)
        if lane and task_lane != lane:
            continue
        if task_lane in in_progress_lanes:
            continue
        candidates.append(task)
    if not candidates:
        return None
    return sorted(candidates, key=lambda t: t.id)[0]


def pick_parallel_batch(limit: int) -> list[Task]:
    """Select up to `limit` pending tasks across non-conflicting lanes."""
    tasks = load_tasks()
    in_progress_lanes = {
        lane_for_phase(t.phase) for t in tasks if t.status == "in_progress"
    }
    used_lanes: set[str] = set(in_progress_lanes)
    batch: list[Task] = []
    for task in sorted(
        [t for t in tasks if t.status == "pending" and dependencies_met(t, tasks)],
        key=lambda t: t.id,
    ):
        if len(batch) >= limit:
            break
        task_lane = lane_for_phase(task.phase)
        if task_lane in used_lanes:
            continue
        batch.append(task)
        used_lanes.add(task_lane)
    return batch
