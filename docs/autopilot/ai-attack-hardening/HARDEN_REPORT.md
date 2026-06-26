# AI attack hardening report

**Pack:** `docs/autopilot/ai-attack-hardening/ai-attack-hardening.json`  
**Date:** 2026-06-26  
**Status:** In progress (1/10 requirements complete)

## Summary

Hardening pass against scripted verify submit, synthetic keystrokes, automation browsers, and join-farm patterns. Phase 1 session binding is shipped; remaining controls are tracked in the pack JSON and `IT_GAP_AUDIT.md`.

## Fixes shipped

| Req | Priority | Control | Implementation | Tests |
|-----|----------|---------|----------------|-------|
| 1 | Critical | **Verify session binding** | Precheck issues `challenge_secret` (stored on token row); submit requires HMAC-SHA256 `challenge_proof` over `{token}:{visitor_id}` | `test_precheck_returns_challenge_secret`, `test_submit_rejects_invalid_challenge`, `test_submit_rejects_reused_token` |
| — | — | **BLOCK submit taxonomy** | Restored missing `block_ban_taxonomy` import on verify submit BLOCK path | `test_submit_block_ban_evasion_auto_deny_not_pending` |

### Session binding flow

1. Browser calls `POST /api/verify/precheck` → server stores `verify_challenge_secret` on the token and returns `challenge_secret` in JSON.
2. `static/verify.js` computes `challenge_proof` via `crypto.subtle` (HMAC-SHA256).
3. `POST /api/verify/submit` rejects missing or invalid proof with HTTP 400 `challenge_invalid` before token claim.
4. Raw API replay without a prior precheck on the same token cannot complete verification.

## In progress / backlog (reqs 2–9)

| Req | Description | Status |
|-----|-------------|--------|
| 2 | Per-token precheck rate limit + visitor_id bind | Not started |
| 3 | Keystroke plausibility + payload bounds | Not started |
| 4 | Precheck oracle reduction + `TRUSTED_PROXY_IPS` | Not started |
| 5 | `automation_flag_mode` channel policy | Not started |
| 6 | Extended env_flags + automation score | Not started |
| 7 | Security wizard automation step | Not started |
| 8 | Join velocity tracker | Not started |
| 9 | Join burst wired into matching | Not started |

## Security presets (current behavior)

Channels configure policy via `/security` wizard. Preset bundles (`open` / `balanced` / `strict`) set ban-evasion and similarity thresholds today. **Strict** lowers auto-deny and flag thresholds (more holds, fewer auto-approves).

When reqs 5–6 land, **strict** channels will additionally escalate automation signals (`webdriver`, synthetic keystrokes, env anomalies) to **pending** or **block** per `automation_flag_mode` instead of flag-only.

## Artifacts

- `docs/plans/ai-attack-hardening-brainstorm.md` — threat model
- `docs/autopilot/ai-attack-hardening/ai-attack-hardening.md` — PRD
- `singulr/services/verify_session.py` — challenge issue/verify helpers
- `tests/verify_helpers.py` — test helper for challenge proofs

## Verification

```
powershell -File scripts\verify.ps1   # 189 tests — PASS
```
