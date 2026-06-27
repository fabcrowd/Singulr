# Repo lead loop (overnight / handoff)

## For the owner (plain language)

**“Run while I’m away”** means the Agent should **keep writing and merging code** (autopilot reqs, tests green), not just sync files to GitHub.

You do **not** need to say: monitored terminal, `notify_on_output`, `AGENT_LOOP_TICK`, etc. Say something like:

> Run while I’m away — ship until production-ready.

Or run `.\scripts\start-repo-lead.ps1` and paste into Agent. The Agent must follow **`.cursor/rules/away-mode.mdc`**.

| Automation | What it does | Ships features? |
|------------|--------------|-----------------|
| **Cursor `/loop` + away-mode rule** | Wakes **this** Agent chat on a timer | **Yes** |
| **Singulr GitHub Sync** (Windows task) | Hourly commit/push if files changed | **No** (sync only) |
| **`overnight-autopilot-loop.ps1`** | Appends lines to a log file | **No** (does not wake Agent) |

---

Copy the **LOOP PROMPT** into a **new Cursor Agent** chat. Enable **auto-run terminal commands**. Read skill: **`senior-singulr-dev`** (`.cursor/skills/senior-singulr-dev/SKILL.md`).

**Overnight / long runs:** Cursor **`/loop`** — Agent arms a **monitored** background shell (`AGENT_LOOP_TICK_REPO_LEAD` + `notify_on_output`). See `.cursor/rules/away-mode.mdc`. Run the LOOP PROMPT once immediately, then again on each tick.

Log-only ticker (optional audit; **does not** wake Agent):

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

**Persist to `tasks/HANDOFF_SUMMARY.md`** (overwrite each build session). The next tick **must read this file first** and continue from **Next up**.

Post when finishing a **loop tick / build session**, when **blocked** (`REPO_LEAD_BLOCKED`), or when **production-ready** (`SINGULR_PRODUCTION_READY`). Do **not** post between items within the same chained turn.

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

File path: **`tasks/HANDOFF_SUMMARY.md`**

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

### TICK handler (`AGENT_LOOP_TICK_overnight` or `AGENT_LOOP_TICK_REPO_LEAD`)

Read **`docs/autopilot/IT_LOOP_PROMPT.md`** TICK HANDLER (or JSON `prompt` on the tick line).

1. **Read `tasks/HANDOFF_SUMMARY.md`** — continue "Next up" first
2. `powershell -File scripts\verify.ps1` — grind until green
3. **Chained build session (same turn):** ship multiple slices — handoff next up → IT_GAP P0→P1→P2 → autopilot eligible → hardening/tests. Do not stop after one item when backlog exists.
4. **Overwrite `tasks/HANDOFF_SUMMARY.md`** with shipped work + concrete "Next up"
5. Stop only per IT_LOOP_PROMPT stop conditions (`SINGULR_PRODUCTION_READY`, `REPO_LEAD_BLOCKED`, verify stuck, backlog exhausted, or ≥2 slices shipped)

Arm loop: `.\scripts\overnight-loop.ps1 -IntervalMinutes 30` (Cursor-monitored foreground; not Start-Job).

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
