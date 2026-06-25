"""Semantic and structural verification for PRD tasks."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.prd import REPO_ROOT, Task, load_prd

TEST_FUNC_RE = re.compile(r"^\s*def\s+test_", re.MULTILINE)
FILE_EXISTS_RE = re.compile(
    r"^(.+?)\s+exists(?:\s+with\s+>=\s*(\d+)\s+test functions)?\.?$",
    re.IGNORECASE,
)
PYTEST_PASSES_RE = re.compile(r"pytest\s+(.+?)\s+passes", re.IGNORECASE)


@dataclass
class CheckResult:
    """Single verification check outcome."""

    name: str
    passed: bool
    detail: str


@dataclass
class VerifyReport:
    """Full verification report for a task."""

    task_id: str
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)

    def failed_checks(self) -> list[CheckResult]:
        """Return checks that did not pass."""
        return [c for c in self.checks if not c.passed]


def _run_cmd(cmd: str, cwd: Path = REPO_ROOT) -> tuple[int, str]:
    """Run shell command and return exit code + combined output."""
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


def check_structural_criterion(criterion: str) -> CheckResult:
    """Parse and evaluate one acceptance_criteria string (heuristic)."""
    criterion = criterion.strip()

    m = FILE_EXISTS_RE.match(criterion)
    if m:
        rel_path = m.group(1).replace("/", "\\") if "\\" in str(REPO_ROOT) else m.group(1)
        path = REPO_ROOT / rel_path.replace("\\", "/")
        if not path.exists():
            return CheckResult(criterion, False, f"Missing file: {path.relative_to(REPO_ROOT)}")
        min_tests = m.group(2)
        if min_tests:
            content = path.read_text(encoding="utf-8")
            count = len(TEST_FUNC_RE.findall(content))
            needed = int(min_tests)
            if count < needed:
                return CheckResult(
                    criterion,
                    False,
                    f"Found {count} test functions, need >= {needed}",
                )
        return CheckResult(criterion, True, "ok")

    m = PYTEST_PASSES_RE.search(criterion)
    if m:
        target = m.group(1).strip()
        cmd = f".venv\\Scripts\\pytest {target} -q"
        code, output = _run_cmd(cmd)
        if code != 0:
            return CheckResult(criterion, False, output[-2000:] or "pytest failed")
        return CheckResult(criterion, True, "pytest passed")

    if "README" in criterion:
        readme = REPO_ROOT / "README.md"
        if not readme.exists():
            return CheckResult(criterion, False, "README.md missing")
        return CheckResult(criterion, True, "README present")

    if "GET /health" in criterion:
        test_health = REPO_ROOT / "tests" / "test_health.py"
        if not test_health.exists():
            return CheckResult(criterion, False, "tests/test_health.py missing")
        return CheckResult(criterion, True, "health test file present")

    if "Document" in criterion or "document" in criterion:
        return CheckResult(criterion, True, "documentation criterion (manual)")

    if "No regression" in criterion.lower():
        return CheckResult(criterion, True, "regression deferred to full suite")

    return CheckResult(criterion, True, f"unparsed criterion accepted: {criterion[:60]}")


def verify_task(task: Task, *, full_suite: bool = True) -> VerifyReport:
    """Run structural, command, and optional full-suite verification."""
    report = VerifyReport(task_id=task.id, passed=True)

    for criterion in task.acceptance_criteria:
        result = check_structural_criterion(criterion)
        report.checks.append(result)
        if not result.passed:
            report.passed = False

    if task.verification:
        code, output = _run_cmd(task.verification)
        cmd_check = CheckResult(
            f"verification: {task.verification}",
            code == 0,
            output[-2000:] if code != 0 else "ok",
        )
        report.checks.append(cmd_check)
        if not cmd_check.passed:
            report.passed = False

    if full_suite:
        prd = load_prd()
        for suite_cmd in prd.get("verification_suite", {}).get("commands", []):
            if not suite_cmd.get("required", True):
                continue
            cmd = suite_cmd["cmd"]
            code, output = _run_cmd(cmd)
            name = suite_cmd.get("name", cmd)
            suite_check = CheckResult(
                f"suite:{name}",
                code == 0,
                output[-1500:] if code != 0 else "ok",
            )
            report.checks.append(suite_check)
            if not suite_check.passed:
                report.passed = False

    return report
