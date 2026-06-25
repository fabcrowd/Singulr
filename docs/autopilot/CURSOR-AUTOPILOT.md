# Cursor Autopilot — Gens-ai workflow without Claude Code CLI

This repo uses the [Gens-ai/autopilot](https://github.com/Gens-ai/autopilot) **task JSON format** and TDD loop, executed by **Cursor Agent** via the Singulr Conductor bridge—not `~/.local/bin/autopilot` or `claude` CLI.

## Gens-ai vs this repo

| Gens-ai (Claude Code) | Singulr (Cursor) |
|----------------------|------------------|
| `/autopilot init` | `autopilot.json` already in repo root |
| `/prd "feature"` | Write `docs/autopilot/<name>/<name>.md` or brainstorm → PRD |
| `/tasks prd.md` | Hand-author or generate `<name>.json` (see examples) |
| `autopilot tasks.json` (fresh session per req) | Agent chat + `LOOP_PROMPT.md` or tick script |
| `/autopilot tasks.json --batch 1` | `python -m orchestrator autopilot next` → one req |
| `autopilot verify` (implicit in hook) | `python -m orchestrator autopilot verify <id>` |
| `AGENTS.md` learnings | `AGENTS.md` + `tasks/lessons.md` |
| `.autopilot/loop-state.md` | `docs/autopilot/*/LOOP_PROMPT.md` + optional tick script |

## Quick start (overnight improve)

```powershell
cd "C:\Users\daroo\repos\Telegram bot"

# 1. Activate task file
python -m orchestrator autopilot use docs/autopilot/overnight-improve/overnight-improve.json

# 2. Baseline must be green
powershell -File scripts\verify.ps1

# 3. Assign next requirement
python -m orchestrator autopilot next

# 4. Open Cursor Agent — paste LOOP PROMPT from:
#    docs/autopilot/overnight-improve/LOOP_PROMPT.md

# 5. Optional: wake every 45m
.\scripts\overnight-loop.ps1 -IntervalMinutes 45
```

## Per-requirement loop (TDD)

For each requirement in `tasks/NEXT_TASK.md`:

1. **Red** — Write failing tests for all `acceptance` items.
2. **Green** — Implement minimally; run feedback loops.
3. **Refactor** — Clean up; loops still green.
4. **Verify** — `python -m orchestrator autopilot verify <id>`
5. **Complete** — `python -m orchestrator autopilot complete <id>`
6. **Notes** — Append to `*-notes.md`; learnings to `AGENTS.md` if needed.
7. **Next** — `python -m orchestrator autopilot next`

### Subagents (use in parallel when independent)

| Skill / agent | Use for |
|---------------|---------|
| `explore` / `parallel-exploring` | Codebase research, test gaps |
| `deep-bug-hunt` | Critical bugs in recent commits |
| `security-review` | Auth, rate limits, exposed routes |
| `grinding-until-pass` | Fix loop until `verify.ps1` green |
| `telegram-bot-architect` | Bot handler UX and test patterns |

## Wrapper scripts

| Script | Purpose |
|--------|---------|
| `scripts/autopilot-cursor.ps1` | `status`, `next`, `verify`, `complete`, `fail`, `use` |
| `scripts/cursor-autopilot-batch.ps1` | One-iteration helper (`--batch 1` equivalent) |
| `scripts/overnight-loop.ps1` | Background tick → `AGENT_LOOP_TICK_overnight_improve` |
| `scripts/overnight-autopilot-loop.ps1` | Generic tick: `-TaskSlug network-trust-registry` |
| `scripts/stop-overnight-loop.ps1` | Stop tick job |
| `scripts/verify.ps1` | Full feedback loop suite |

## Repo lead agent (overnight handoff)

Skill: `.cursor/skills/senior-singulr-dev/SKILL.md` — acting tech lead; makes design calls, **researches on the web** (WebSearch/WebFetch), implements findings with tests, runs autopilot, delegates to other skills/subagents. Logs research URLs and decisions in `*-notes.md`.

Handoff: paste LOOP PROMPT from `docs/autopilot/REPO_LEAD_LOOP_PROMPT.md` into a new Agent chat, or open `tasks/REPO_LEAD_HANDOFF.txt`.

```powershell
.\scripts\overnight-autopilot-loop.ps1 -TaskSlug network-trust-registry -IntervalMinutes 45
```

## Task files in this repo

| Feature | JSON | Status |
|---------|------|--------|
| Production hardening | `production-hardening/production-hardening.json` | Done |
| Overnight ops | `overnight-ops/overnight-ops.json` | Done |
| **Overnight improve** | `overnight-improve/overnight-improve.json` | **Active** |

## Creating a new feature (PRD → tasks → loop)

1. **PRD** — `docs/autopilot/<feature>/<feature>.md` (goals, non-goals, requirements prose).
2. **Tasks** — `docs/autopilot/<feature>/<feature>.json` with `requirements[]`, `acceptance[]`, `tdd`, `dependsOn`.
3. **Loop prompt** — `docs/autopilot/<feature>/LOOP_PROMPT.md` (copy-paste for Agent).
4. **Activate** — `python -m orchestrator autopilot use docs/autopilot/<feature>/<feature>.json`
5. **Run** — Agent + `next` / `verify` / `complete` until `status` shows all done.

Use `/prd` and `/tasks` slash commands in Cursor when available; they follow the same schema as Gens-ai.

## Stuck / thrashing

- Same error 3× → `python -m orchestrator autopilot fail <id> --reason "..."`
- Log in `*-notes.md` and `AGENTS.md` Gotchas
- Continue with `autopilot next` if another req is eligible

## Done signals

| Task file | Output when complete |
|-----------|---------------------|
| `overnight-ops` | `OVERNIGHT_OPS_COMPLETE` |
| `overnight-improve` | `OVERNIGHT_IMPROVE_COMPLETE` |
| `tasks/prd.json` (Conductor) | `SINGULR_SHIP` |

Always run `scripts/verify.ps1` before declaring done.
