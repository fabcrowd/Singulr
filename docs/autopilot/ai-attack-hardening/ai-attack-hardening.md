# PRD: AI attack hardening

**Codename:** `ai-attack-hardening`  
**Status:** Draft — from brainstorm  
**Sources:** [docs/plans/ai-attack-hardening-brainstorm.md](../../plans/ai-attack-hardening-brainstorm.md)  
**Related:** `IT_GAP_AUDIT.md`, `deep-harden` pack, social profiling

---

## 1. Overview

Harden Singulr's join verification path against **automated and AI-driven bypass**: scripted submit APIs, synthetic keystrokes, headless browsers, verify oracles, and coordinated Telegram join farms. Deliver **server-verifiable** challenges, expanded automation signals, and channel-configurable responses — without breaking the minimal member UX for legitimate users.

## 2. Goals

1. **No trust in raw submit JSON** — cryptographic bind between precheck and submit.
2. **Detect synthetic typing** — plausibility checks on keystroke dynamics.
3. **Close precheck oracle** — per-token limits; reduced client intel leakage.
4. **Channel policy for automation** — flag / pending / block per signal class.
5. **Join burst awareness** — velocity signals for farm waves.
6. **Full regression suite** — every control has pytest coverage.

## 3. Non-goals

- Third-party CAPTCHA required for all channels
- In-repo ML training pipeline
- Blocking Telegram Premium users by default

## 4. Requirements mapping

See `ai-attack-hardening.json` — 10 core requirements across Phases 1–3 from brainstorm.

## 5. Verification

`powershell -File scripts\verify.ps1` after each requirement.
