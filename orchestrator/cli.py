"""Conductor CLI — status, dispatch, verify, complete, fail."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from orchestrator.autopilot_cursor import (
    append_note,
    load_task_file,
    mark_requirement,
    pick_next_requirement,
    set_active_task,
    status_summary,
    verify_requirement,
    write_next_requirement,
)
from orchestrator.dispatch import build_brief, write_brief, write_next_task_md
from orchestrator.lessons import append_lesson, write_golden_packet
from orchestrator.runtime import get_agent_runtime, runtime_label, set_agent_runtime
from orchestrator.prd import (
    REPO_ROOT,
    get_task,
    lane_for_phase,
    load_tasks,
    pick_next_task,
    pick_parallel_batch,
    update_task_status,
)
from orchestrator.verifier import verify_task


def _safe_print(text: str) -> None:
    """Print text without crashing on Windows consoles that lack Unicode glyphs."""
    encoding = sys.stdout.encoding or "utf-8"
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(encoding, errors="replace").decode(encoding))


def cmd_status(_: argparse.Namespace) -> int:
    """Print task dashboard."""
    tasks = load_tasks()
    by_status: dict[str, list[str]] = {}
    for t in tasks:
        by_status.setdefault(t.status, []).append(t.id)
    print("Singulr Conductor status")
    print("=" * 40)
    for status in ["in_progress", "pending", "done", "blocked"]:
        ids = by_status.get(status, [])
        if ids:
            print(f"  {status}: {', '.join(ids)}")
    pending = len(by_status.get("pending", []))
    done = len(by_status.get("done", []))
    print(f"\n  Progress: {done}/{len(tasks)} done, {pending} pending")
    in_prog = [t for t in tasks if t.status == "in_progress"]
    if in_prog:
        print("\n  In progress:")
        for t in in_prog:
            print(f"    {t.id} [{lane_for_phase(t.phase)}] {t.title}")
    if pending == 0 and all(t.status in {"done", "blocked"} for t in tasks):
        print("\n  All tasks done or blocked. Run scripts/verify.ps1 then emit SINGULR_SHIP.")
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    """Assign next task."""
    task = pick_next_task(lane=args.lane)
    if not task:
        print("No eligible pending task.")
        return 1
    update_task_status(task.id, "in_progress")
    path = write_next_task_md(task)
    write_brief(task)
    print(f"Assigned {task.id}: {task.title}")
    print(f"  Lane: {lane_for_phase(task.phase)}")
    print(f"  Brief: orchestrator/briefs/{task.id}.md")
    print(f"  NEXT_TASK: {path.relative_to(path.parent.parent)}")
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    """Write parallel agent briefs."""
    batch = pick_parallel_batch(args.parallel)
    if not batch:
        print("No parallel batch available.")
        return 1
    paths = []
    for task in batch:
        update_task_status(task.id, "in_progress")
        p = write_brief(task)
        paths.append(p)
        print(f"  {task.id} [{lane_for_phase(task.phase)}] -> {p}")
    print(f"\nDispatched {len(batch)} agents. Open {len(batch)} Cursor tasks with each brief.")
    print("Cursor Task prompt template:")
    print('  Read orchestrator/briefs/T00X.md and execute. Verify then complete or fail.')
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify a task."""
    task = get_task(args.task_id)
    if not task:
        print(f"Unknown task {args.task_id}")
        return 1
    report = verify_task(task, full_suite=not args.quick)
    print(json.dumps(
        {
            "task_id": report.task_id,
            "passed": report.passed,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail[:200]} for c in report.checks],
        },
        indent=2,
    ))
    return 0 if report.passed else 1


def cmd_complete(args: argparse.Namespace) -> int:
    """Verify and mark task done."""
    task = get_task(args.task_id)
    if not task:
        print(f"Unknown task {args.task_id}")
        return 1
    report = verify_task(task, full_suite=True)
    if not report.passed:
        write_golden_packet(task, reason="complete rejected: verification failed", report=report)
        print("Verification failed. Task remains in_progress. See orchestrator/runs/")
        return 1
    update_task_status(task.id, "done")
    print(f"OK {task.id} complete")
    return 0


def cmd_fail(args: argparse.Namespace) -> int:
    """Record failure and lesson."""
    task = get_task(args.task_id)
    if not task:
        print(f"Unknown task {args.task_id}")
        return 1
    report = verify_task(task, full_suite=False) if args.verify else None
    path = write_golden_packet(task, reason=args.reason, report=report)
    append_lesson(task, symptom=args.reason, root_cause=args.reason)
    update_task_status(task.id, "pending", notes=args.reason)
    print(f"Recorded failure: {path}")
    print(f"Task {task.id} reset to pending. Lesson appended.")
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    """Print or write brief for a task."""
    task = get_task(args.task_id)
    if not task:
        return 1
    if args.write:
        p = write_brief(task)
        print(p)
    else:
        print(build_brief(task))
    return 0


def cmd_runtime(args: argparse.Namespace) -> int:
    """Show or set agent runtime (cursor | claude-code)."""
    if args.set:
        try:
            set_agent_runtime(args.set)
        except ValueError as exc:
            print(exc)
            return 1
        print(f"Agent runtime: {args.set} ({runtime_label(args.set)})")
        print("Docs: docs/AGENT_RUNTIME.md")
        return 0
    rt = get_agent_runtime()
    print(f"runtime: {rt}")
    print(f"label: {runtime_label(rt)}")
    doc = "docs/autopilot/CLAUDE-CODE-AUTOPILOT.md" if rt == "claude-code" else "docs/autopilot/CURSOR-AUTOPILOT.md"
    print(f"guide: {doc}")
    return 0


def cmd_autopilot_use(args: argparse.Namespace) -> int:
    """Set active autopilot task file for agent sessions."""
    path = Path(args.task_file)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        print(f"Task file not found: {path}")
        return 1
    rel = set_active_task(path)
    print(f"Active autopilot task: {rel}")
    print("Run: python -m orchestrator autopilot next")
    return 0


def cmd_autopilot_status(_: argparse.Namespace) -> int:
    """Print autopilot requirement dashboard."""
    try:
        _safe_print(status_summary())
    except FileNotFoundError as exc:
        print(exc)
        return 1
    return 0


def cmd_autopilot_next(_: argparse.Namespace) -> int:
    """Assign next autopilot requirement to tasks/NEXT_TASK.md."""
    try:
        task = load_task_file()
    except FileNotFoundError as exc:
        print(exc)
        return 1
    req = pick_next_requirement(task)
    if req is None:
        print("No eligible requirements. All done or blocked.")
        return 1
    path = write_next_requirement(task, req)
    append_note(task, f"Assigned req {req.id} to Cursor (NEXT_TASK)")
    print(f"Assigned requirement {req.id}: {req.description[:80]}")
    print(f"  Brief: orchestrator/briefs/AP-{req.id}.md")
    print(f"  NEXT_TASK: {path.relative_to(REPO_ROOT)}")
    print("Open Cursor Agent and implement. Then verify + complete.")
    return 0


def cmd_autopilot_verify(args: argparse.Namespace) -> int:
    """Verify one autopilot requirement."""
    report = verify_requirement(args.req_id, full_suite=not args.quick)
    print(
        json.dumps(
            {
                "req_id": report.req_id,
                "passed": report.passed,
                "checks": [
                    {"name": c.name, "passed": c.passed, "detail": c.detail[:200]}
                    for c in report.checks
                ],
            },
            indent=2,
        )
    )
    return 0 if report.passed else 1


def cmd_autopilot_complete(args: argparse.Namespace) -> int:
    """Verify and mark autopilot requirement done."""
    report = verify_requirement(args.req_id, full_suite=True)
    if not report.passed:
        print("Verification failed. Requirement not marked done.")
        return 1
    mark_requirement(args.req_id, passes=True)
    task = load_task_file()
    append_note(task, f"Completed req {args.req_id}")
    print(f"OK requirement {args.req_id} complete")
    return 0


def cmd_autopilot_fail(args: argparse.Namespace) -> int:
    """Mark requirement stuck and log note."""
    mark_requirement(args.req_id, passes=False, stuck=True, reason=args.reason)
    task = load_task_file()
    append_note(task, f"FAILED req {args.req_id}: {args.reason}")
    print(f"Requirement {args.req_id} marked stuck. See notes file.")
    return 0


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Singulr Conductor orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Task dashboard")
    p_status.set_defaults(func=cmd_status)

    p_next = sub.add_parser("next", help="Assign next PRD task")
    p_next.add_argument("--lane", default=None)
    p_next.set_defaults(func=cmd_next)

    p_dispatch = sub.add_parser("dispatch", help="Parallel agent briefs")
    p_dispatch.add_argument("--parallel", type=int, default=4)
    p_dispatch.set_defaults(func=cmd_dispatch)

    p_verify = sub.add_parser("verify", help="Verify PRD task")
    p_verify.add_argument("task_id")
    p_verify.add_argument("--quick", action="store_true", help="Skip full suite")
    p_verify.set_defaults(func=cmd_verify)

    p_complete = sub.add_parser("complete", help="Verify and mark PRD task done")
    p_complete.add_argument("task_id")
    p_complete.set_defaults(func=cmd_complete)

    p_fail = sub.add_parser("fail", help="Record PRD failure + lesson")
    p_fail.add_argument("task_id")
    p_fail.add_argument("--reason", required=True)
    p_fail.add_argument("--verify", action="store_true")
    p_fail.set_defaults(func=cmd_fail)

    p_brief = sub.add_parser("brief", help="Show PRD task brief")
    p_brief.add_argument("task_id")
    p_brief.add_argument("--write", action="store_true")
    p_brief.set_defaults(func=cmd_brief)

    p_runtime = sub.add_parser("runtime", help="Show or set agent runtime (cursor | claude-code)")
    p_runtime.add_argument("set", nargs="?", help="cursor or claude-code")
    p_runtime.set_defaults(func=cmd_runtime)

    ap = sub.add_parser("autopilot", help="Gens-ai autopilot tasks (Cursor or Claude Code bridge)")
    ap_sub = ap.add_subparsers(dest="ap_command", required=True)

    ap_use = ap_sub.add_parser("use", help="Set active task JSON file")
    ap_use.add_argument("task_file")
    ap_use.set_defaults(func=cmd_autopilot_use)

    ap_status = ap_sub.add_parser("status", help="Requirement dashboard")
    ap_status.set_defaults(func=cmd_autopilot_status)

    ap_next = ap_sub.add_parser("next", help="Assign next requirement to NEXT_TASK")
    ap_next.set_defaults(func=cmd_autopilot_next)

    ap_verify = ap_sub.add_parser("verify", help="Verify requirement")
    ap_verify.add_argument("req_id")
    ap_verify.add_argument("--quick", action="store_true")
    ap_verify.set_defaults(func=cmd_autopilot_verify)

    ap_complete = ap_sub.add_parser("complete", help="Verify and complete requirement")
    ap_complete.add_argument("req_id")
    ap_complete.set_defaults(func=cmd_autopilot_complete)

    ap_fail = ap_sub.add_parser("fail", help="Mark requirement stuck")
    ap_fail.add_argument("req_id")
    ap_fail.add_argument("--reason", required=True)
    ap_fail.set_defaults(func=cmd_autopilot_fail)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
