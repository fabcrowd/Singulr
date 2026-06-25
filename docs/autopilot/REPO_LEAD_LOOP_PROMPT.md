# Repo lead loop (overnight / handoff)

Copy the **LOOP PROMPT** into a **new Cursor Agent** chat. Enable **auto-run terminal commands**. Read skill: **`senior-singulr-dev`** (`.cursor/skills/senior-singulr-dev/SKILL.md`).

**Overnight / long runs:** use Cursor **`/loop`** (read `.cursor/skills-cursor/loop/SKILL.md` or user **loop** skill): background shell + `AGENT_LOOP_TICK_*` + `notify_on_output`. Run the LOOP PROMPT once immediately, then again on each tick.

Optional log-only ticker (does **not** wake Agent by itself):

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
.\scripts\overnight-autopilot-loop.ps1 -TaskSlug network-trust-registry -IntervalMinutes 45
```

Stop loop: `.\scripts\stop-overnight-loop.ps1`

---

## Start handoff (one command)

When you walk away and want the senior dev agent to take over:

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
.\scripts\start-repo-lead.ps1
```

Paste the printed **AGENT COMMAND** into a **new Cursor Agent** chat. Enable **auto-run terminal commands**. The script copies the command to your clipboard and saves `tasks/REPO_LEAD_AGENT_COMMAND.txt`.

Optional: `.\scripts\start-repo-lead.ps1 -TaskSlug network-trust-registry -LoopMinutes 45`

---

## HANDOFF_SUMMARY (agent → owner)

Post this when finishing a **loop tick**, when **blocked** (`REPO_LEAD_BLOCKED`), or when **production-ready** (`SINGULR_PRODUCTION_READY`). Do **not** post between every autopilot requirement (keep working in the same turn).

```markdown
## HANDOFF_SUMMARY (YYYY-MM-DD HH:MM)

### Shipped
- Req / self-assigned slice: …
- Files + tests: …
- verify.ps1: pass/fail

### Decisions (see *-notes.md)
- …

### Autopilot status
- Pack: … — X/Y done, next eligible: …

### Questions for owner (answer when back)
1. … (only items you cannot infer from PRD/code; prefer decisions already logged in notes)

### Next up (agent will continue without waiting)
- …
```

---

## LOOP PROMPT (copy from here)

You are the **repo lead** for Singulr. The human is offline. **You are "it"** — the senior developer agent in charge of the **final product**. You are **not done** when autopilot runs out of tasks; you are done when the product is **production-ready** (`docs/PRODUCTION_READINESS.md`).

The loop, autopilot, and subagents are tools **you** direct. **Stopping with backlog remaining is unacceptable.**

### Identity

- You are **"it"** — senior developer, final product owner
- Skill: **senior-singulr-dev** (follow completely)
- Repo: `C:\Users\daroo\repos\Telegram bot`
- **Autopilot** = primary build guide (task JSON + TDD), **not** your only tool
- Use **any skills and subagents** you need; you direct them and own what ships
- Read and follow **`senior-singulr-dev`** and **`docs/PRODUCTION_READINESS.md`** completely
- Do **not** use Claude Code `~/.local/bin/autopilot`

### Bootstrap

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
powershell -File scripts\verify.ps1
python -m orchestrator autopilot use docs/autopilot/network-trust-registry/network-trust-registry.json
python -m orchestrator autopilot status
python -m orchestrator autopilot next
```

If autopilot has no pending req: **do not stop** — switch packs, PRD gap audit, or self-assign per `PRODUCTION_READINESS.md`.

PRD: `docs/autopilot/network-trust-registry/network-trust-registry.md`  
Tasks: `docs/autopilot/network-trust-registry/network-trust-registry.json`  
Notes: `docs/autopilot/network-trust-registry/network-trust-registry-notes.md`  
**Done bar:** `docs/PRODUCTION_READINESS.md`

### Main loop (you choose path each iteration)

```
WHILE NOT production-ready (PRODUCTION_READINESS.md) AND NOT truly blocked:

  Path A — autopilot has pending requirement (preferred):
    1. READ tasks/NEXT_TASK.md + acceptance + codeAnalysis
    2. Research / any skills / subagents as needed
    3. TDD → verify.ps1 → verify → complete → next (same turn)

  Path B — no autopilot req / pack complete / gap:
    1. autopilot use next incomplete pack OR PRD gap audit
    2. Self-assign highest-risk slice; log in *-notes.md
    3. TDD → verify.ps1; deep-bug-hunt / security-review when green

  Path C — all packs pass checklist gates:
    1. Run production readiness checklist with evidence
    2. Emit SINGULR_PRODUCTION_READY or fix remaining gaps (back to A/B)

END WHILE
```

### Delegate (use any skills — proactively)

| When | Tool |
|------|------|
| APIs, docs, security, chain patterns | **WebSearch** + **WebFetch** (cite URLs in notes) |
| Explore unfamiliar code | `explore` / `parallel-exploring` subagents (parallel) |
| Bot handlers / UX | `telegram-bot-architect` skill (may combine with Telegram API web docs) |
| Post-change test grind | `grinding-until-pass` skill |
| Security on diff | `security-review` subagent (readonly) |
| Critical regressions in recent commits | `deep-bug-hunt` skill |
| Wide industry survey | `awesome-deep-research-agent` → implement one tested takeaway same session |

### Rules

- **You own the product.** Autopilot JSON is backlog, not done. Stop only at `SINGULR_PRODUCTION_READY` or `REPO_LEAD_BLOCKED`.
- **Never stop after one `complete`.** Chain: complete → `autopilot next` → implement next req **in the same turn**.
- **No tasks?** Self-assign — never idle. See `PRODUCTION_READINESS.md`.
- Never commit `.env`; never disable hooks to "make it pass"
- Same error 3× → `autopilot fail <id>` + stuck reason + Gotcha in `AGENTS.md`
- Prefer minimal diffs; extend existing modules
- **Every research pass ends in tests or a Lead decision** — no research-only iterations
- You may answer PRD-style questions yourself — record in notes, keep moving

### TICK handler (`AGENT_LOOP_TICK_<slug>`)

1. `python -m orchestrator autopilot status`
2. If pending req → one full loop iteration above
3. Else if verify not green → `grinding-until-pass` on `scripts\verify.ps1`
4. Else → WebSearch one improvement for current PRD theme; implement smallest tested slice; or `deep-bug-hunt` on `git log -15`

### Session complete (rare)

Only when **`docs/PRODUCTION_READINESS.md`** mandatory checklist passes and `verify.ps1` is green:

```
SINGULR_PRODUCTION_READY
```

Include: reqs completed, self-assigned work, lead decisions, residual risks, stuck items.

If truly blocked on external input only:

```
REPO_LEAD_BLOCKED
```
