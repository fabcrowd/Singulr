# network-trust-registry Progress Notes

## Current State
- Last completed: requirement 5 (verify API + channel policy)
- Working on: requirement 6
- Blockers: none

## Files Modified
- singulr/domain/ban_taxonomy.py — BanCategory, BanSeverity enums
- singulr/domain/__init__.py — package marker
- singulr/models.py — Ban.category/severity; ChannelSecuritySettings
- singulr/services/bans.py — record_ban() accepts category/severity
- singulr/services/channel_policy.py — EffectivePolicy + get_effective_channel_policy()
- singulr/config.py — ban_evasion_auto_deny_threshold, local_similarity_flag_threshold defaults
- singulr/api/admin.py — list_bans returns category/severity
- tests/test_ban_taxonomy.py — enum, persistence, defaults, admin API tests
- singulr/services/matching.py — Decision.PENDING, dual-threshold ban evasion, policy param
- singulr/api/verify.py — pending decision payload
- singulr/bot/handlers.py — pending review handler
- tests/test_matching.py — auto-deny + pending cases
- singulr/services/telegram_actions.py — log_to_ops_channel, resolve_admin_ops_chat_id, notify_user_denied
- singulr/bot/handlers.py — permit_/deny_ callbacks, pending/block ops routing
- singulr/config.py — admin_ops_chat_id env
- tests/test_bot_ops_workflow.py — ops channel Permit/Deny workflow
- orchestrator/verifier.py — fix false-positive on prose containing "exists"
- tests/test_orchestrator.py — regression for verifier prose parsing

## Lead decision (2026-06-25)
- Context: req 1 needs legacy-safe defaults for existing ban rows.
- Chose: `category=other`, `severity=medium` as ORM column defaults (Python + server_default) so inserts without taxonomy still satisfy non-null columns.
- Deferred: ban callback UI and chain category mapping (req 6, 8–9).

## Lead decision (2026-06-25) — req 2
- Context: per-channel policy loader needs env fallbacks before wizard ships (req 7).
- Chose: `balanced` preset defaults — auto-deny 0.92, flag 0.85, network mode `read`; nullable threshold columns on DB row fall back to config when partially set.
- Deferred: network score thresholds, auto-reject categories, wizard persistence (req 7, 10–12).

## Lead decision (2026-06-25) — req 3
- Context: ban-evasion needs BLOCK vs PENDING split; existing FLAG retained for IP/env signals.
- Chose: `Decision.PENDING` for medium similarity on a *different* `telegram_user_id`; stylometry loop fixed to attribute `matched_ban` per banned user row.
- Deferred: full ops Permit/Deny workflow (req 4); verify submit still returns pending payload for bot wiring.

## Lead decision (2026-06-25) — req 4
- Context: ops chat separate from audit log channel; pending must not ban until Deny.
- Chose: `log_to_ops_channel()` resolves chat from `ADMIN_OPS_CHAT_ID` env → channel policy `admin_ops_chat_id`; callbacks `permit_{channel_id}_{user_id}` / `deny_{channel_id}_{user_id}`; auto-deny audit posts without keyboard.
- Deferred: category-aware denial templates (req 5+).

## Session Log
- [2026-06-25] Task JSON generated from PRD via /tasks
- [2026-06-25 05:03 UTC] Assigned req 1 to Cursor (NEXT_TASK)
- [2026-06-25] Req 1 shipped: ban taxonomy enums, Ban model columns, record_ban + admin list_bans; verify.ps1 green (74 tests)
- [2026-06-25] Req 2 shipped: ChannelSecuritySettings, EffectivePolicy loader, config thresholds; verify.ps1 green (78 tests)
- [2026-06-25] Req 3 shipped: dual-threshold ban evasion, Decision.PENDING, policy-aware check_known_bad; verify.ps1 green (80 tests)
- [2026-06-25] Req 4 shipped: ops channel Permit/Deny, audit-only auto-deny; verify.ps1 green (85 tests)
- [2026-06-25] Req 5 shipped: verify API wired to channel policy + pending/block payloads; verify.ps1 green (87 tests)

## Dependency summary

## Dependency summary

```
1 Ban taxonomy
2 ChannelSecuritySettings ──► 3 Dual-threshold matching ──► 4 Ops workflow ──► 5 Verify API
         │                           │
         └──► 7 Security wizard      └──► 14 Reverification
         │
8 BanRegistry.sol ──► 9 ChainClient ──► 10 Network score ──► 11 Network write
                              │
6 Ban callback (from 1)       └──► 13 Reinstatement
7 + 10 ──► 12 Wizard network steps
```

## already-done (no task required)

- Profile model with status, fingerprint_hash, keystroke_profile
- Basic check_known_bad with BLOCK for exact match and chain boolean
- apply_verification_decision approve/flag/block paths
- log_to_channel formatters and internal ban API auth

- [2026-06-25 05:03 UTC] Assigned req 1 to Cursor (NEXT_TASK)

- [2026-06-25 05:03 UTC] Assigned req 1 to Cursor (NEXT_TASK)

- [2026-06-25 05:03 UTC] Assigned req 1 to Cursor (NEXT_TASK)

- [2026-06-25 05:03 UTC] Assigned req 1 to Cursor (NEXT_TASK)

- [2026-06-25 05:04 UTC] Assigned req 1 to Cursor (NEXT_TASK)

- [2026-06-25 05:04 UTC] Completed req 1

- [2026-06-25 05:04 UTC] Assigned req 2 to Cursor (NEXT_TASK)

- [2026-06-25 05:04 UTC] Assigned req 2 to Cursor (NEXT_TASK)

- [2026-06-25 05:04 UTC] Assigned req 2 to Cursor (NEXT_TASK)

- [2026-06-25 05:05 UTC] Assigned req 2 to Cursor (NEXT_TASK)

- [2026-06-25 05:05 UTC] Assigned req 2 to Cursor (NEXT_TASK)

- [2026-06-25 05:05 UTC] Assigned req 2 to Cursor (NEXT_TASK)

- [2026-06-25 05:05 UTC] Assigned req 2 to Cursor (NEXT_TASK)

- [2026-06-25 05:05 UTC] Assigned req 2 to Cursor (NEXT_TASK)

- [2026-06-25 05:05 UTC] Completed req 2

- [2026-06-25 05:05 UTC] Assigned req 3 to Cursor (NEXT_TASK)

- [2026-06-25 05:07 UTC] Assigned req 3 to Cursor (NEXT_TASK)

- [2026-06-25 05:07 UTC] Assigned req 3 to Cursor (NEXT_TASK)

- [2026-06-25 05:07 UTC] Assigned req 3 to Cursor (NEXT_TASK)

- [2026-06-25 05:07 UTC] Completed req 3

- [2026-06-25 05:07 UTC] Assigned req 4 to Cursor (NEXT_TASK)

- [2026-06-25 05:07 UTC] Assigned req 4 to Cursor (NEXT_TASK)

- [2026-06-25 05:09 UTC] Assigned req 4 to Cursor (NEXT_TASK)

- [2026-06-25 05:09 UTC] Assigned req 4 to Cursor (NEXT_TASK)

- [2026-06-25 05:09 UTC] Assigned req 4 to Cursor (NEXT_TASK)

- [2026-06-25 05:09 UTC] Completed req 4

- [2026-06-25 05:09 UTC] Assigned req 5 to Cursor (NEXT_TASK)

- [2026-06-25 05:10 UTC] Assigned req 5 to Cursor (NEXT_TASK)

- [2026-06-25 05:10 UTC] Assigned req 5 to Cursor (NEXT_TASK)

- [2026-06-25 05:10 UTC] Assigned req 5 to Cursor (NEXT_TASK)

- [2026-06-25 05:10 UTC] Completed req 5

- [2026-06-25 10:41 UTC] Assigned req 14 to Cursor (NEXT_TASK)

- [2026-06-25 10:41 UTC] Assigned req 14 to Cursor (NEXT_TASK)

- [2026-06-25 10:42 UTC] Assigned req 14 to Cursor (NEXT_TASK)

- [2026-06-25 10:42 UTC] Assigned req 14 to Cursor (NEXT_TASK)

- [2026-06-25 11:04 UTC] Assigned req 14 to Cursor (NEXT_TASK)

- [2026-06-25 11:04 UTC] Assigned req 14 to Cursor (NEXT_TASK)
