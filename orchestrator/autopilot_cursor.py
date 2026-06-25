"""Cursor-native Autopilot — Gens-ai task JSON without Claude Code CLI."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.prd import BRIEFS_DIR, NEXT_TASK_PATH, REPO_ROOT
from orchestrator.runtime import get_agent_runtime, runtime_label
from orchestrator.verifier import CheckResult, check_structural_criterion

ACTIVE_PATH = REPO_ROOT / ".autopilot" / "active.json"
CONFIG_PATH = REPO_ROOT / "autopilot.json"
NOTES_SUFFIX = "-notes.md"


@dataclass
class Requirement:
    """One autopilot requirement from a task JSON file."""

    id: str
    description: str
    acceptance: list[str]
    depends_on: list[str]
    passes: bool
    stuck: bool
    tdd: dict[str, Any]
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Requirement:
        """Parse requirement object."""
        return cls(
            id=str(data["id"]),
            description=data.get("description", ""),
            acceptance=list(data.get("acceptance", [])),
            depends_on=[str(x) for x in data.get("dependsOn", [])],
            passes=bool(data.get("passes", False)),
            stuck=bool(data.get("stuck", False)),
            tdd=dict(data.get("tdd", {})),
            raw=data,
        )


@dataclass
class AutopilotTaskFile:
    """Loaded autopilot task JSON."""

    path: Path
    name: str
    description: str
    goals: list[str]
    requirements: list[Requirement]
    raw: dict[str, Any]

    def requirement(self, req_id: str) -> Requirement | None:
        """Find requirement by id."""
        for req in self.requirements:
            if req.id == req_id:
                return req
        return None

    def save(self) -> None:
        """Write requirements back to disk."""
        self.path.write_text(json.dumps(self.raw, indent=2) + "\n", encoding="utf-8")


def load_config() -> dict[str, Any]:
    """Load project autopilot.json."""
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def active_task_path() -> Path | None:
    """Return active task file path if configured."""
    if not ACTIVE_PATH.exists():
        return None
    data = json.loads(ACTIVE_PATH.read_text(encoding="utf-8"))
    rel = data.get("taskFile")
    if not rel:
        return None
    return REPO_ROOT / str(rel).replace("\\", "/")


def set_active_task(task_file: Path) -> Path:
    """Point Cursor autopilot at a task JSON file."""
    rel = task_file.resolve().relative_to(REPO_ROOT.resolve())
    ACTIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_PATH.write_text(
        json.dumps({"taskFile": rel.as_posix()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return rel


def load_task_file(path: Path | None = None) -> AutopilotTaskFile:
    """Load the active or given autopilot task file."""
    target = path or active_task_path()
    if target is None:
        msg = "No active task file. Run: python -m orchestrator autopilot use <task.json>"
        raise FileNotFoundError(msg)
    if not target.is_absolute():
        target = REPO_ROOT / target
    raw = json.loads(target.read_text(encoding="utf-8"))
    reqs = [Requirement.from_dict(r) for r in raw.get("requirements", [])]
    return AutopilotTaskFile(
        path=target,
        name=raw.get("name", target.stem),
        description=raw.get("description", ""),
        goals=list(raw.get("goals", [])),
        requirements=reqs,
        raw=raw,
    )


def _deps_satisfied(task: AutopilotTaskFile, req: Requirement) -> bool:
    """True when all dependsOn requirements have passes=true."""
    for dep_id in req.depends_on:
        dep = task.requirement(dep_id)
        if dep is None or not dep.passes:
            return False
    return True


def pick_next_requirement(task: AutopilotTaskFile) -> Requirement | None:
    """Lowest-id incomplete requirement with satisfied dependencies."""
    pending = [
        r
        for r in task.requirements
        if not r.passes and not r.stuck and _deps_satisfied(task, r)
    ]
    if not pending:
        return None
    return sorted(pending, key=lambda r: r.id)[0]


def notes_path(task: AutopilotTaskFile) -> Path:
    """Progress notes markdown beside the task file."""
    return task.path.with_name(f"{task.path.stem}{NOTES_SUFFIX}")


def append_note(task: AutopilotTaskFile, line: str) -> None:
    """Append timestamped line to notes file."""
    path = notes_path(task)
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    existing = path.read_text(encoding="utf-8") if path.exists() else f"# {task.name} notes\n\n"
    path.write_text(f"{existing}\n- [{stamp}] {line}\n", encoding="utf-8")


def build_requirement_brief(task: AutopilotTaskFile, req: Requirement) -> str:
    """Agent brief for one autopilot requirement (TDD)."""
    acceptance = "\n".join(f"- {c}" for c in req.acceptance)
    tdd = req.tdd
    test_phase = tdd.get("test", {})
    impl_phase = tdd.get("implement", {})
    refactor_phase = tdd.get("refactor", {})

    return f"""# Autopilot requirement — {req.id} ({task.name})

## Description
{req.description}

## Acceptance criteria
{acceptance}

## TDD workflow (strict)
1. **Red** — {test_phase.get('description', 'Write failing tests for all acceptance criteria')}. Commit when tests fail for the right reason.
2. **Green** — {impl_phase.get('description', 'Minimal implementation until tests pass')}. Commit when green.
3. **Refactor** — {refactor_phase.get('description', 'Clean up; keep tests green')}. Commit if needed.

## Verify before complete
```powershell
python -m orchestrator autopilot verify {req.id}
python -m orchestrator autopilot complete {req.id}
```

## On failure
```powershell
python -m orchestrator autopilot fail {req.id} --reason "short summary"
```

## After complete (same turn)
```powershell
python -m orchestrator autopilot next
```
Read the new `tasks/NEXT_TASK.md` and **continue implementing** — do not end the turn with only a summary.

**No eligible req?** Follow `docs/PRODUCTION_READINESS.md` — switch packs or self-assign. Do not stop.

## Project goals
{chr(10).join('- ' + g for g in task.goals)}

Task file: `{task.path.relative_to(REPO_ROOT)}`
"""


def write_next_requirement(task: AutopilotTaskFile, req: Requirement) -> Path:
    """Write NEXT_TASK.md and brief for agent session injection."""
    brief = build_requirement_brief(task, req)
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    brief_path = BRIEFS_DIR / f"AP-{req.id}.md"
    brief_path.write_text(brief, encoding="utf-8")
    rt = get_agent_runtime()
    if rt == "claude-code":
        runner_note = (
            f"> Claude Code / Gens-ai autopilot (`autopilot {task.path.relative_to(REPO_ROOT)}`) "
            f"or bridge (`python -m orchestrator autopilot next`). "
            f"Runtime: {runtime_label(rt)}. Do not edit manually.\n\n"
        )
    else:
        runner_note = (
            f"> Cursor autopilot (`python -m orchestrator autopilot next`). "
            f"Runtime: {runtime_label(rt)}. Do not edit manually.\n\n"
        )
    NEXT_TASK_PATH.write_text(
        f"# NEXT TASK — Autopilot {task.name} / req {req.id}\n\n"
        f"{runner_note}"
        f"{brief}",
        encoding="utf-8",
    )
    return NEXT_TASK_PATH


def _run_cmd(cmd: str) -> tuple[int, str]:
    """Run shell command in repo root."""
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


def run_feedback_loops(config: dict[str, Any]) -> list[CheckResult]:
    """Run enabled feedback loops from autopilot.json."""
    loops = config.get("feedbackLoops", {})
    checks: list[CheckResult] = []
    for name, spec in loops.items():
        if not spec.get("enabled", True):
            continue
        cmd = spec.get("command")
        if not cmd:
            continue
        code, output = _run_cmd(cmd)
        checks.append(
            CheckResult(
                name=f"feedback:{name}",
                passed=code == 0,
                detail=output[:500] if output else f"exit {code}",
            )
        )
    return checks


@dataclass
class AutopilotVerifyReport:
    """Verification report for one requirement."""

    req_id: str
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)


def verify_requirement(req_id: str, *, full_suite: bool = True) -> AutopilotVerifyReport:
    """Check acceptance criteria and feedback loops."""
    task = load_task_file()
    req = task.requirement(req_id)
    if req is None:
        return AutopilotVerifyReport(req_id, False, [CheckResult("exists", False, "unknown requirement")])

    checks: list[CheckResult] = []
    for criterion in req.acceptance:
        checks.append(check_structural_criterion(criterion))

    if full_suite:
        checks.extend(run_feedback_loops(load_config()))

    passed = all(c.passed for c in checks)
    return AutopilotVerifyReport(req_id, passed, checks)


def mark_requirement(req_id: str, *, passes: bool, stuck: bool = False, reason: str = "") -> None:
    """Update requirement flags in task JSON."""
    task = load_task_file()
    for idx, raw_req in enumerate(task.raw.get("requirements", [])):
        if str(raw_req.get("id")) != req_id:
            continue
        raw_req["passes"] = passes
        if stuck:
            raw_req["stuck"] = True
            if reason:
                raw_req["blockedReason"] = reason
        task.requirements[idx] = Requirement.from_dict(raw_req)
        break
    task.save()


def status_summary() -> str:
    """Human-readable dashboard."""
    task = load_task_file()
    total = len(task.requirements)
    done = sum(1 for r in task.requirements if r.passes)
    stuck = sum(1 for r in task.requirements if r.stuck)
    pending = total - done - stuck
    lines = [
        f"Autopilot (Cursor) — {task.name}",
        "=" * 40,
        f"  Task file: {task.path.relative_to(REPO_ROOT)}",
        f"  Progress: {done}/{total} done, {pending} pending, {stuck} stuck",
    ]
    for req in sorted(task.requirements, key=lambda r: r.id):
        state = "done" if req.passes else ("stuck" if req.stuck else "pending")
        lines.append(f"    [{state}] {req.id}: {req.description[:70]}")
    nxt = pick_next_requirement(task)
    if nxt:
        lines.append(f"\n  Next eligible: {nxt.id}")
    elif done == total:
        lines.append("\n  All requirements complete. Run scripts/verify.ps1")
    return "\n".join(lines)
