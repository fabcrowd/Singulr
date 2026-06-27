# Singulr production readiness bar

**Audience:** repo-lead / senior-singulr-dev agent ("it").  
**Purpose:** You stop work only when this bar is met — not when one autopilot pack ends or one requirement completes.

Autopilot task JSON is a **backlog organizer**, not the definition of done. You own the **product**.

## Stop signal (only these)

Emit **`SINGULR_PRODUCTION_READY`** (and a short human summary) **only when every mandatory item below is true**.

If blocked on external input (secrets, deploy credentials, human product call), emit **`REPO_LEAD_BLOCKED`** with what is needed — not a victory lap.

**Never** stop because:
- One requirement or pack completed
- `autopilot next` returned no eligible req (switch packs or self-assign — see below)
- You wrote a nice summary
- Context is getting long (arm `/loop` or continue next tick)

## Mandatory checklist

| # | Gate | How to verify |
|---|------|----------------|
| 1 | **Green suite** | `powershell -File scripts\verify.ps1` passes |
| 2 | **Active PRD shipped** | `network-trust-registry` task JSON: all requirements `passes: true` or documented `stuck` with reason |
| 3 | **Improvement backlog** | `overnight-improve` task JSON: same (audit, critical fixes, test gaps) |
| 4 | **PRD core flows** | Join → verify → approve / pending ops / auto-deny; admin ban with category; `/security` wizard persists policy (per PRD phases) |
| 5 | **Ops path** | Pending → Permit/Deny in ops chat; auto-deny audit-only; denial DMs |
| 6 | **Security pass** | `security-review` on API/auth/admin paths; no open critical findings |
| 7 | **Correctness pass** | `deep-bug-hunt` on recent commits; critical issues fixed or documented |
| 8 | **Deploy path** | `docs/DEPLOY.md` steps still match repo (compose, env vars, health) |

## When autopilot has no eligible requirement

Do **not** idle. In order:

1. `python -m orchestrator autopilot status` on **active** pack
2. If pack complete → `autopilot use` the **next incomplete** pack under `docs/autopilot/` (priority: `network-trust-registry` → `overnight-improve`)
3. If all packs complete → **IT gap audit**: `docs/autopilot/IT_GAP_AUDIT.md` — confirm open P0→P2 rows against code; mark DONE if shipped
4. Pick the **highest-risk gap**; TDD + `verify.ps1`; log Lead decision
5. No open IT gaps → `deep-bug-hunt`, `security-review`, expand tests (handlers, watcher, verify, admin API)

## Task pack priority

| Order | Pack | Role |
|-------|------|------|
| 1 | `network-trust-registry` | Core product PRD |
| 2 | `overnight-improve` | Audit, critical bugs, coverage |
| 3 | Gaps from PRD audit | Self-assigned slices |
| — | `production-hardening`, `overnight-ops` | Already done; re-verify if touched |

## Lead documents before `SINGULR_PRODUCTION_READY`

In `docs/autopilot/network-trust-registry/network-trust-registry-notes.md` (or active pack notes):

```markdown
## Production readiness review (YYYY-MM-DD)
- Checklist: 1–8 pass/fail with evidence
- Residual risks: (honest; non-blocking vs blocking)
- Deferred (post-launch): ...
```
