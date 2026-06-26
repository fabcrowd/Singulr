# Deep-harden report

**Pack:** `docs/autopilot/deep-harden/deep-harden.json`  
**Date:** 2026-06-26  
**Status:** Complete (5/5 requirements)

## Summary

Overnight deep debugging and hardening pass on verify submit, bot admin callbacks, and external social API paths. Three security issues fixed with regression tests; full suite green at **185 tests**.

## Fixes shipped

| ID | Severity | Issue | Fix | Test |
|----|----------|-------|-----|------|
| C1 | Critical | Double verify submit race (token reused before mark) | `claim_verification_token()` atomic UPDATE | `test_hardening::test_claim_token_prevents_second_submit`, `test_api_verify::test_submit_rejects_reused_token` |
| H1 | High | Permit/deny/details callbacks lacked admin check | `_require_ops_admin()` via `get_chat_member` | `test_hardening::test_permit_callback_rejects_non_admin` |
| H2 | High | Malformed external API JSON could crash provider | `json.loads` + typed parse → `SocialProfileProviderError` | `test_social_external::test_external_api_provider_raises_on_malformed_json` |

## Hardening verified (no code change needed)

- **Social fail_closed:** `test_social_profile::test_fail_closed_forces_pending_on_provider_error` — provider errors force PENDING when policy is `fail_closed`.
- **External API secrets:** Logs never include `SOCIAL_API_KEY` or Bearer token — `test_social_external::test_external_api_provider_does_not_log_api_key`.
- **External API timeout:** 1.5s default; HTTP errors raise `SocialProfileProviderError` — existing test.

## Artifacts

- `docs/autopilot/deep-harden/audit.md` — severity-classified findings
- Regression tests in `tests/test_hardening.py`, `tests/test_api_verify.py`, `tests/test_social_external.py`, `tests/test_bot_ops_workflow.py`

## Residual watch items

- Expired token claim consumes token without processing (acceptable one-shot semantics).

## Verification

```
powershell -File scripts\verify.ps1   # pytest + ruff + compile — PASS
```
