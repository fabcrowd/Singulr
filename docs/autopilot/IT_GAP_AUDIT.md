# IT gap audit — testing & hardening backlog

**Date:** 2026-06-26  
**Author:** repo-lead review (senior-singulr-dev)  
**Context:** All autopilot packs show complete and `verify.ps1` is green (186 tests). Green ≠ production-ready. This document is the **self-assigned backlog** when autopilot has no eligible requirements.

**Production readiness:** Not `SINGULR_PRODUCTION_READY` — checklist items 6–8 need work (security pass depth, contract tests, gap coverage).

---

## Executive summary

| Area | Status |
|------|--------|
| Verify gate | pytest + ruff + hardhat **compile** only — no contract tests, no mypy, no E2E |
| Test depth | Strong on verify submit, tokens, social profiling, reinstatement **service** layer |
| Test gaps | Admin HTTP (`unban`, appeals list), watcher pipeline, wizard abort/toggles, `verify_ban`, `details_` callback, contract logic |
| Security | Prior critical fixes landed (token race, ops callbacks, legacy approve/ban) |
| Open security | Wizard admin re-check on callbacks, precheck oracle, X-Forwarded-For trust, fail-open defaults |

---

## P0 — Do first (security + untested critical paths)

| ID | Risk | Location | Action |
|----|------|----------|--------|
| P0-1 | **High** | `security_wizard.py` callbacks | Re-check `is_channel_admin()` on **every** wizard step, especially `confirm_selected` before `upsert_channel_security_settings` | **DONE** (2026-06-26 tick 21) |
| P0-2 | **High** | `api/verify.py` precheck | Per-token rate limit; reduce oracle (`allowed`/`ip_flagged` brute-force on leaked links) | **DONE** — `allow_precheck_for_token`, `tests/test_verify_rate_limit.py` |
| P0-3 | **High** | `api/verify.py` `_client_ip` | Only trust `X-Forwarded-For` from configured proxy IPs | **DONE** — `TRUSTED_PROXY_IPS` in config, `tests/test_api_verify.py` |
| P0-4 | **Critical** | `POST /api/admin/unban` | HTTP tests: 200, 400, 404, 401 | **DONE** — `tests/test_admin_api.py` |
| P0-5 | **Critical** | `services/verify_ban.py` | Table-driven tests for `block_ban_taxonomy` | **DONE** — `tests/test_verify_ban.py` |
| P0-6 | **Critical** | `handlers.py` `details_` + `format_admin_profile_details` | Test "More details" callback end-to-end | **DONE** — `tests/test_bot_ops_workflow.py` |
| P0-7 | **Critical** | `api/security.py` `require_admin_key` | Test 503 when `ADMIN_API_KEY` unset | **DONE** — `tests/test_admin_api.py` |
| P0-8 | **Critical** | `handlers.py` `on_channel_message` | Test stylometry / message log ingestion | **DONE** — `tests/test_bot_handlers.py` + `tests/test_watcher.py` |

---

## P1 — Hardening + important test gaps

| ID | Risk | Location | Action |
|----|------|----------|--------|
| P1-1 | **High** | `matching.py` stylometry evasion branch | Test BLOCK/PENDING at configured thresholds |
| P1-2 | **High** | `security_wizard.py` | Test cancel / `sec_confirm_no` does not persist partial policy |
| P1-3 | **High** | `GET /api/admin/appeals` | List + auth tests |
| P1-4 | **High** | `domain/chain_mapping.py` | Parametrize ordinals vs `BanRegistry.sol` enums |
| P1-5 | **Critical** | `contracts/BanRegistry.sol` | Add Hardhat tests; add `npx hardhat test` to CI / verify gate |
| P1-6 | **Medium** | `api/verify.py` `admin_ban` | Pydantic body; validate category/severity; 422 on bad input | **DONE** — `InternalBanBody` model added 2026-06-28 |
| P1-7 | **Medium** | `api/verify.py` submit response | Strip internal fields from client JSON (risk_factors, matched_ban_id) |
| P1-8 | **Medium** | `services/blockchain.py` | Fail-closed on RPC error → PENDING + ops alert; test init failure path | **DONE** (2026-06-26) |
| P1-9 | **Medium** | `services/rate_limit.py` | Redis/shared limiter for multi-worker deploy; admin route limits |
| P1-10 | **Medium** | `api/verify.py` `SubmitBody.keystrokes` | `max_length` + request body size cap |
| P1-11 | **Medium** | `tokens.py` `create_token` | Fix count race (serializable tx or `FOR UPDATE`) |
| P1-12 | **High** | `handlers.py` `run_watcher_job` | Mock matches → assert `log_to_channel` posts |

---

## P2 — Coverage expansion

| ID | Area | Action |
|----|------|--------|
| P2-1 | `matching.py` | IP-hash ban FLAG without velocity; network block→PENDING policy documented + tested |
| P2-2 | `channel_policy.py` | `format_policy_summary` snapshot; null-field defaults |
| P2-3 | `api/verify.py` | `privacy_required` 400; precheck 410 expired token |
| P2-4 | `telegram_actions.py` | `resolve_admin_ops_chat_id` fallback chain; `notify_user_result` held copy |
| P2-5 | `handlers.py` | `deny_` non-admin rejection test; ban flow expired message |
| P2-6 | `security_wizard.py` | Instant-ban chip toggles; social on/off chips; `sec_delta_keep` |
| P2-7 | `ban_flow.py` | Unit tests for `parse_ban_*` malformed data |
| P2-8 | `hashing.py` | Direct tests for `hash_ip`, stable outputs |
| P2-9 | `bot/runtime.py` | `get_application` bridge smoke test |
| P2-10 | `static/verify.html` | Self-host FingerprintJS or `referrerpolicy=no-referrer`; token not in Referer to CDN |

---

## What `verify.ps1` does NOT enforce

1. Behavioral depth on admin API, watcher, wizard abort paths  
2. Smart contract **logic** (compile only today)  
3. Real Telegram or chain integration (all mocked)  
4. Static typing (no mypy/pyright in gate)  
5. Production rate limiting across replicas  

---

## Fail-open vs fail-closed inventory

| Component | Current | Recommendation |
|-----------|---------|----------------|
| Social providers (default) | fail-open | Consider default `fail_closed` for strict channels |
| Chain RPC down | fail-open (not banned) | PENDING + alert |
| Network high score | PENDING not BLOCK | Document; strict preset may auto-block |
| Ops admin API error | fail-closed (deny) | OK |
| Empty `ADMIN_API_KEY` | 503 | OK — needs test |

---

## Suggested autopilot pack (self-assign)

**Active:** `docs/autopilot/ai-attack-hardening/ai-attack-hardening.json` (from brainstorm `docs/plans/ai-attack-hardening-brainstorm.md`)

Create `docs/autopilot/test-hardening/test-hardening.json` with requirements:

1. Admin API test suite (`unban`, appeals, 503 disabled key)  
2. `verify_ban` + `details_` callback tests  
3. Security wizard admin re-check + cancel tests  
4. Watcher pipeline tests (`on_channel_message`, `run_watcher_job`)  
5. Hardhat BanRegistry tests in CI  
6. Precheck hardening (per-token limit + proxy IP trust)  
7. Gap audit report update + `verify.ps1` green  

---

## Loop directive update

When all autopilot packs are complete, **do not idle on green verify**.

**Overnight loop:** `@it` runs via `scripts/overnight-loop.ps1` (Cursor-monitored, `AGENT_LOOP_TICK_overnight`). Full prompt: `docs/autopilot/IT_LOOP_PROMPT.md`.

Each tick:
1. Body-of-work review (`git log -20`, audit table vs code/tests)
2. Highest open **P0 → P1 → P2** item — TDD, `verify.ps1`, mark **DONE**
3. If no open gaps — `deep-bug-hunt`, `security-review`, expand handler/watcher/verify tests
4. Prefer eligible autopilot req if one exists

Pick highest P0 item, TDD, `verify.ps1`, log in `*-notes.md`, repeat.
