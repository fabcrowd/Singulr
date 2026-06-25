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

## Setup (first time on this machine)

```powershell
cd "C:\Users\daroo\repos\Telegram bot"
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
npm install
powershell -File scripts\verify.ps1
```
