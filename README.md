# Singulr

Telegram community verification that stops banned users from rejoining on new accounts — by fingerprinting their device, analyzing how they type, and building a writing-style profile over time. Ban records can be mirrored to **Adiri testnet** (Telcoin) for a tamper-proof shared blacklist.

## Two core functions

1. **The Gate** — On join, the bot restricts the user, DMs a verification link, and runs fingerprint + keystroke checks against banned records.
2. **The Watcher** — The bot logs channel messages and builds stylometry profiles per `telegram_user_id`, periodically flagging members who match banned writing patterns.

Phone numbers and usernames are ignored for detection. A new SIM creates a new Telegram account, but the same device and typing style still match.

## Stack

| Layer | Tech |
|-------|------|
| Bot | python-telegram-bot |
| API | FastAPI |
| Database | PostgreSQL (SQLite for local dev) |
| Chain | Solidity + Hardhat on Adiri (Chain ID 2017) |
| Fingerprint | FingerprintJS Pro (optional) or OSS v4 CDN; browser fallback hash if both fail |

## Device fingerprinting (Pro vs OSS)

The verification page (`static/verify.js`) calls `/api/verify/precheck` first. The response may include `fingerprint_public_key` when `FINGERPRINT_PUBLIC_KEY` is set in `.env`.

| Config | Loader | Behavior |
|--------|--------|----------|
| `FINGERPRINT_PUBLIC_KEY` set | FingerprintJS Pro (via CDN + public key from precheck) | Higher-accuracy `visitorId` + `requestId` for matching |
| Key unset | [FingerprintJS OSS v4](https://openfpcdn.io/fingerprintjs/v4/iife.min.js) in `verify.html` | Free client-side fingerprint |
| JS blocked / error | Built-in `fallbackVisitorId()` hash | Weaker signal; still allows flow |

Set `FINGERPRINT_SECRET_KEY` only on the server if you add Pro Server API validation later. MVP stores `visitor_id` from the client result.

| Frontend | Single-page `/verify` |

See [docs/DEPLOY.md](docs/DEPLOY.md) for production Docker Compose deployment.

## Quick start

### 1. Environment

```bash
cp .env.example .env
# Edit .env — at minimum set BOT_TOKEN, CHANNEL_ID, LOG_CHANNEL_ID, PUBLIC_BASE_URL
```

### 2. Database (optional Docker)

```bash
docker compose up -d db
```

For local dev without Docker, leave `DATABASE_URL` as SQLite default in `.env.example`.

### 3. Python

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
```

### 4. Smart contract (optional until chain is needed)

```bash
npm install
npm run compile
# Add WALLET_PRIVATE_KEY to .env, get test TEL from thirdweb faucet
npm run deploy:adiri
# Put CONTRACT_ADDRESS in .env
```

### 5. Run

```bash
uvicorn singulr.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker (production)

Build and run without baking secrets into the image — pass env at runtime:

```bash
docker build -t singulr .
docker run --rm -p 8000:8000 \
  -e BOT_TOKEN=... \
  -e CHANNEL_ID=... \
  -e LOG_CHANNEL_ID=... \
  -e PUBLIC_BASE_URL=http://localhost:8000 \
  singulr
```

Health check: `curl http://localhost:8000/health`

### 6. Telegram setup

1. Create bot via [@BotFather](https://t.me/BotFather) — `@singulr_bot`
2. Add bot to your channel as admin: **Ban users**, **Invite users**, **Restrict members**
3. Enable **Approve new members** (join requests) on the channel
4. Create private **Singulr Mod Log** channel; add bot with post permission
5. Forward a message from each channel to [@userinfobot](https://t.me/userinfobot) for IDs

### 7. Test

```bash
pytest
curl http://localhost:8000/health
```

Open `http://localhost:8000/verify?token=...` after triggering `/verify` in the bot DM.

## Verification sentence

Users type exactly:

> Welcome to Singulr! I confirm that I am joining as myself, with 1 account only. I agree to the rules and will keep this account secure.

Mobile and desktop keystroke profiles are stored separately.

## Project layout

```
contracts/          BanRegistry.sol
scripts/            Hardhat deploy
singulr/
  api/              Verification endpoints
  bot/              Join flow, watcher, admin callbacks
  services/         Matching, stylometry, chain, bans
static/             Verification page
tests/
```

## Security notes

- **Rotate `BOT_TOKEN` before production** if it was ever shared in chat.
- Store secrets only in `.env` (gitignored).
- IP hashes are stored, never raw IPs.
- Chain writes are optional until `CONTRACT_ADDRESS` + `WALLET_PRIVATE_KEY` are set.

## Agent tooling (Cursor or Claude Code)

This repo ships autopilot task JSON, PRDs, and a shared verify gate for **either** agent host.

| Action | Command |
|--------|---------|
| Set runtime | `.\scripts\set-agent-runtime.ps1 cursor` or `claude-code` |
| Hub doc | [docs/AGENT_RUNTIME.md](docs/AGENT_RUNTIME.md) |
| Senior dev handoff | `.\scripts\start-repo-lead.ps1` |
| Orchestrator | `python -m orchestrator autopilot use\|status\|next\|verify\|complete` |

- **Cursor:** `.cursor/skills/`, [docs/autopilot/CURSOR-AUTOPILOT.md](docs/autopilot/CURSOR-AUTOPILOT.md)
- **Claude Code:** [CLAUDE.md](CLAUDE.md), reinstall Gens-ai skills, [docs/autopilot/CLAUDE-CODE-AUTOPILOT.md](docs/autopilot/CLAUDE-CODE-AUTOPILOT.md)

Default runtime in `.autopilot/runtime.json` is `cursor` (safe to commit; change per machine).

## Later phases (not in MVP)

- reCAPTCHA v3, IPQualityScore
- 24h member audit, cross-channel instant trigger
- Admin web dashboard, multi-tenant SaaS
- Probabilistic profile matching UI (side-by-side view)
- Periodic re-verification intervals
