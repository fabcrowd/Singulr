# RECOVERY — D: drive corruption

**Canonical workspace (use this):**

```
C:\Users\daroo\repos\Telegram bot
```

Legacy mirror (same tree, hyphenated name): `C:\Users\daroo\repos\Telegram-bot`

**Do not use** `D:\repos\Telegram bot` — D: volume has WinError 433 / read-write failures.

## Fix D: drive (optional, run as Administrator)

```powershell
chkdsk D: /F
```

## Open in Cursor

File → Open Folder → `C:\Users\daroo\repos\Telegram bot`

## Autopilot (Cursor — not Claude Code)

Gens-ai task JSON runs via **Cursor Agent** + Conductor. Full guide: `docs/autopilot/CURSOR.md`.

**Tonight:** `docs/autopilot/overnight-ops/LOOP_PROMPT.md` — paste into Agent before sleep.

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
.\scripts\autopilot-cursor.ps1 status
.\scripts\autopilot-cursor.ps1 next
```

Do **not** use `~/.local/bin/autopilot` (Claude Code CLI) for this repo.

## Setup (first time)
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
npm install
powershell -File scripts\verify.ps1
```
