# Overnight improve — final report

**Date:** 2026-06-25  
**Pack:** `overnight-improve` (7/7 requirements complete)  
**Suite:** `powershell -File scripts\verify.ps1` — **143 pytest**, ruff clean, Hardhat **5** contract tests

## Shipped in this pack

| Req | Deliverable |
|-----|-------------|
| 1 | `research.md` — architecture dossier + prioritized backlog |
| 2 | `audit.md`; secured `POST /api/internal/ban` with `X-Admin-Key` |
| 3 | `tests/test_bot_handlers.py` — start, approve, flag, join-request paths |
| 4 | Expanded `tests/test_watcher.py`; watcher ignores overturned bans |
| 5 | Submit rate-limit 429 test; JSON access log test |
| 6 | `start_command` token quota handling; timing-safe admin key compare |
| 7 | This report + `tasks/lessons.md` update |

## Network-trust-registry (parallel)

All **14/14** requirements complete in the same session window, including:

- `BanRegistry.sol` with registrar ACL (`onlyRegistrar`)
- Security wizard v2 (network mode + category multi-select)
- Hybrid reinstatement (`local_unban`, decay, appeals API)
- Schema patches in `init_db()` for upgraded deployments

## Residual risks (non-blocking for local/staging)

- `ChainClient.record_ban` / `overturn_ban` remain stubs until chain signing is wired
- `ADMIN_TELEGRAM_ID` unset — `/reverify` bot command disabled until owner sets it
- Production chain deploy requires registrar wallet on `BanRegistry.setRegistrar`
- Away-mode still needs Cursor-open monitored loop or Cloud Agents

## Verify command

```powershell
powershell -File scripts\verify.ps1
npm test
```
