"""Agent runtime selection: Cursor vs Claude Code."""

from __future__ import annotations

import json
from typing import Literal

from orchestrator.prd import REPO_ROOT

RuntimeName = Literal["cursor", "claude-code"]

RUNTIME_PATH = REPO_ROOT / ".autopilot" / "runtime.json"
VALID_RUNTIMES: frozenset[str] = frozenset({"cursor", "claude-code"})


def get_agent_runtime() -> RuntimeName:
    """Return active agent runtime (default: cursor)."""
    if not RUNTIME_PATH.exists():
        return "cursor"
    try:
        data = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
        name = str(data.get("runtime", "cursor")).strip().lower()
        if name in VALID_RUNTIMES:
            return name  # type: ignore[return-value]
    except (json.JSONDecodeError, OSError):
        pass
    return "cursor"


def set_agent_runtime(name: str) -> RuntimeName:
    """Persist agent runtime to .autopilot/runtime.json."""
    normalized = name.strip().lower()
    if normalized not in VALID_RUNTIMES:
        allowed = ", ".join(sorted(VALID_RUNTIMES))
        msg = f"runtime must be one of: {allowed}"
        raise ValueError(msg)
    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PATH.write_text(
        json.dumps({"runtime": normalized}, indent=2) + "\n",
        encoding="utf-8",
    )
    return normalized  # type: ignore[return-value]


def runtime_label(name: RuntimeName | None = None) -> str:
    """Human-readable runtime name."""
    rt = name or get_agent_runtime()
    return "Claude Code" if rt == "claude-code" else "Cursor"
