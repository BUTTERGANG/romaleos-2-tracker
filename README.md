# ROMALEOS 2 Tracker 👟

Nike Romaleos 2 price tracker and listing finder — powered by the eBay Browse API with Discord alerts.

Track listings, filter by size/price/condition, and get notified when your perfect pair drops.

## Features

- **Live eBay Listings** — Searches eBay for Nike Romaleos 2 with automatic size extraction
- **Filter & Sort** — By price, condition, size, and listing freshness
- **Smart Watches** — Set up alerts for specific sizes and price ranges
- **Discord Notifications** — Get pinged when a matching listing appears (configurable webhook)
- **Background Polling** — Automatically checks for new listings every 30 minutes
- **Shareable** — Web UI hosted anywhere (Replit, VPS, Railway)

## Quick Start

```bash
# Clone
git clone https://github.com/BUTTERGANG/romaleos-2-tracker.git
cd romaleos-2-tracker

# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Edit .env with your eBay API credentials
# Then run:
uvicorn app.main:app --host 0.0.0.0 --port 8003
```

Open http://localhost:8003

## Configuration

| Variable | Required | Description |
|---|---|---|
| `EBAY_CLIENT_ID` | ✅ | eBay Developer App ID (Client ID) |
| `EBAY_CLIENT_SECRET` | ✅ | eBay Developer App Secret (Client Secret) |
| `DISCORD_WEBHOOK_URL` | ❌ | Discord channel webhook for alerts |
| `POLL_INTERVAL_MINUTES` | ❌ | Background scan frequency (default 30) |

## API Endpoints

| Path | Description |
|---|---|
| `GET /` | Web UI — listing grid with filters |
| `GET /watches` | Web UI — manage price/size watches |
| `GET /api/listings` | JSON — all active listings |
| `GET /api/stats` | JSON — aggregate stats |
| `POST /api/refresh` | Force immediate eBay poll |
| `GET /health` | Health check |

## Replit Deployment

1. Create a new Python Repl from this repo
2. Add secrets in the Replit Secrets tab:
   - `EBAY_CLIENT_ID`
   - `EBAY_CLIENT_SECRET`
   - `DISCORD_WEBHOOK_URL` (optional)
3. The app auto-starts via the `[replit]` config

## License

MIT — BUTTERGANG