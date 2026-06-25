# Singulr Conductor — multi-agent orchestrator

Replaces token-burning Ralph loops with **parallel lanes**, **semantic verification**, and a **lessons loop**.

## Architecture

```
tasks/prd.json          Task backlog (source of truth)
tasks/lanes.json        Parallel lane definitions (up to 16 agents)
tasks/lessons.md        Failure memory (injected every session)
orchestrator/briefs/    Per-agent prompts (fresh context each task)
orchestrator/runs/      Golden packets on failure
.cursor/hooks/          Fast verification hooks
```

## Quick commands

```powershell
# Dashboard
python -m orchestrator status

# Assign next task (writes tasks/NEXT_TASK.md)
python -m orchestrator next

# Spawn N parallel agent briefs (independent lanes only)
python -m orchestrator dispatch --parallel 4

# Verify task (structural + pytest + acceptance criteria)
python -m orchestrator verify T001

# Mark done after verify passes
python -m orchestrator complete T001

# Record failure + lesson + golden packet
python -m orchestrator fail T001 --reason "pytest timeout"

# Full suite
powershell -File scripts/verify.ps1
```

## Parallel agents in Cursor

1. `python -m orchestrator dispatch --parallel 4`
2. Open 4 chats or use **Task** tool with each brief from `orchestrator/briefs/T00X.md`
3. Each agent gets **one task**, **one lane**, **no shared context** (cheap + clean)
4. When agents finish: `python -m orchestrator verify T00X` then `complete T00X`
5. `python -m orchestrator status` shows what's left

### Why this beats Ralph

| Ralph | Conductor |
|-------|-----------|
| Same bloated context every loop | Fresh brief per task |
| Re-reads entire plan | Reads one task + lessons only |
| Token burn while "thinking it's done" | Exit only after `verify` passes |
| Single thread | Up to 16 parallel lanes |
| No failure memory | `lessons.md` + golden packets |

## Semantic verification

`orchestrator verify` runs three layers:

1. **Structural** — files exist, test count thresholds, forbidden patterns
2. **Command** — task `verification` + full `verify.ps1`
3. **Semantic** — parses `acceptance_criteria` strings into checks

Failed semantic checks write a golden packet to `orchestrator/runs/<task_id>/`.

## Cursor hooks (auto)

| Hook | Behavior |
|------|----------|
| `sessionStart` | Injects NEXT_TASK + recent lessons |
| `stop` | Reminds agent to run `verify` before marking done |
| `afterShellExecution` | Captures pytest/ruff failures into runs/ |

Enable in Cursor → Settings → Hooks (project `.cursor/hooks.json`).

## Agent prompt (single task)

Use the generated brief, or:

```text
Read orchestrator/briefs/T001.md only. Implement that task.
When done run: python -m orchestrator verify T001
If pass: python -m orchestrator complete T001
If fail: python -m orchestrator fail T001 --reason "<output>"
Do not start other tasks.
```

## Completion

When `python -m orchestrator status` shows all tasks `done` or `blocked` and `verify.ps1` passes:

```text
SINGULR_SHIP
```

## Phase 2

Create `tasks/prd-phase2.json` — do not append to phase 1 prd.
