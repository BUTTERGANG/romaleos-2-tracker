# ROMALEOS 2 Tracker 👟

Nike Romaleos 2 price tracker and listing finder — powered by the eBay Browse API with Discord alerts.

Track listings, filter by size/price/condition, and get notified when your perfect pair drops.

## Features

- **Live eBay listings** — searches eBay for Nike Romaleos 2 with automatic US-size extraction from titles
- **Filter & sort** — by price range, condition, size, and newest / price / ending-soonest
- **Freshness-aware** — every listing shows a relative age ("7h ago"), new listings get a **NEW** badge, and the dashboard shows when data was last synced
- **Smart watches** — alerts for a specific size (or size range) and price range
- **Discord notifications** — get pinged once per matching listing (configurable webhook)
- **Background polling** — checks eBay every 30 minutes; also polls immediately on startup if the cache is empty
- **eBay-compliant caching** — stale listings are hidden after 6h and deleted after 24h; API calls are throttled well under eBay's daily limit
- **Shareable** — web UI hostable anywhere (Replit, VPS, Railway)

## Quick Start

```bash
git clone https://github.com/BUTTERGANG/romaleos-2-tracker.git
cd romaleos-2-tracker

python -m venv .venv && .venv/bin/pip install -r requirements.txt

cp .env.example .env      # then edit .env with your eBay API credentials

.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 5000
```

Open <http://localhost:5000>. The `.env` file is loaded automatically (via `python-dotenv`).

Without eBay credentials the app still runs — it serves whatever is in the local
cache (`romaleos.db`) and disables live search and polling.

## Configuration

All configuration is via environment variables (or `.env`).

### eBay API

| Variable | Required | Default | Description |
|---|---|---|---|
| `EBAY_CLIENT_ID` | ✅ | — | eBay Developer App ID / Client ID (alias: `APP_ID`) |
| `EBAY_CLIENT_SECRET` | ✅ | — | eBay Developer Cert ID / Client Secret (alias: `CERT_ID`) |
| `EBAY_MARKETPLACE` | ❌ | `EBAY_US` | eBay marketplace ID sent as `X-EBAY-C-MARKETPLACE-ID` |
| `EBAY_CURRENCY` | ❌ | `USD` | Display currency |
| `EBAY_USER_AGENT` | ❌ | `romaleos-2-tracker/1.0 …` | `User-Agent` sent on eBay requests |
| `SEARCH_QUERY` | ❌ | `Nike Romaleos 2` | Base search query (free-text search refines *within* this) |

### Alerts & scheduling

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_WEBHOOK_URL` | ❌ | — | Discord channel webhook for alerts |
| `POLL_INTERVAL_MINUTES` | ❌ | `30` | Background poll frequency |

### Data freshness / eBay compliance

| Variable | Required | Default | Description |
|---|---|---|---|
| `LISTING_STALE_HOURS` | ❌ | `6` | Hide listings not re-seen within N hours |
| `LISTING_PURGE_HOURS` | ❌ | `24` | Delete listings not re-seen within N hours |
| `LIVE_SEARCH_CACHE_SECONDS` | ❌ | `120` | Min gap between page-load-triggered eBay calls, per query+sort |

### App

| Variable | Required | Default | Description |
|---|---|---|---|
| `HOST` | ❌ | `0.0.0.0` | Bind host (used by `python -m app.main`) |
| `PORT` | ❌ | `8003` | Bind port (Replit overrides this to `5000`) |
| `SECRET_KEY` | ❌ | `change-me-in-production` | Reserved for future session use |
| `DATABASE_URL` | ❌ | `sqlite:///romaleos.db` | Informational; the app uses `romaleos.db` directly |

## How it works

```
                 ┌─────────────┐   every POLL_INTERVAL_MINUTES (+ once on startup if empty)
                 │  scheduler  │──────────────┐
                 └─────────────┘              ▼
  browser ──▶ FastAPI ──▶ SQLite (romaleos.db) ◀── eBay Browse API (OAuth2 client-credentials)
                 │             ▲
                 │             └── page-load live search (throttled, scoped to SEARCH_QUERY)
                 ▼
          Discord webhook  ◀── watch matcher (runs on every poll)
```

- **Token handling** — an application (client-credentials) OAuth2 token is fetched
  on demand and cached in memory until ~1 minute before expiry.
- **Retention** — after every poll the app marks listings not seen within
  `LISTING_STALE_HOURS` as inactive and deletes those past `LISTING_PURGE_HOURS`,
  per eBay's [API License Agreement](https://developer.ebay.com/develop/apis/api-license-agreement)
  (displayed data must be < 6h old; unavailable items must be removed).
- **Rate limiting** — the scheduler makes ~48 calls/day; page-load searches are
  throttled and otherwise served from SQLite, keeping usage far below the Browse
  API's [5,000 calls/day](https://developer.ebay.com/develop/apis/api-call-limits).
  A `429` response is retried once, honoring `Retry-After` (capped at 10s).
- **Size extraction** — US sizes 3–18 are parsed from titles only when preceded by
  an explicit marker (`US`, `Size`, `Men's`, …), so style codes like `476927-600`
  are ignored.
- **Blocking work** (eBay HTTP, Discord, SQLite writes) runs in a worker thread so
  it never stalls the event loop.

## Discord alerts

This is an **incoming webhook**, not a gateway bot — the app only posts messages
to one channel per webhook. No bot token, no slash commands, no message reading.

**Setup:**

1. In Discord: **Server Settings → Integrations → Webhooks → New Webhook**.
2. Pick the channel, **Copy Webhook URL**.
3. Set it as `DISCORD_WEBHOOK_URL` (env var, `.env`, or Replit Secret) and restart.
4. Verify with `curl -X POST http://localhost:8003/api/test-discord` (or the
   **Test** button on the Watches page).

**Per-watch channel:** each watch can carry its own webhook URL (field on the
create form) to route that watch's alerts to a different channel; blank uses the
global one.

**Delivery behaviour:**

- Alerts are matched during each poll and sent **batched** — up to 10 embeds per
  request — so a burst of matches costs a handful of calls, not one each.
- `429` responses are retried honoring `retry_after`; transient `5xx`/network
  errors get bounded exponential backoff (4 attempts).
- Each `(watch, listing)` pair fires **once** — the `notifications` table is the
  ledger. A batch that fails all retries is left unrecorded and retried on the
  next poll rather than lost.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Dashboard — listing grid with filters |
| `GET` | `/watches` | Manage price/size watches |
| `POST` | `/watches/add` | Create a watch (form) |
| `POST` | `/watches/{id}/toggle` | Pause / resume a watch |
| `POST` | `/watches/{id}/delete` | Delete a watch |
| `GET` | `/api/listings?search=&sort=&limit=` | JSON — fresh listings + `as_of` timestamp |
| `GET` | `/api/stats` | JSON — aggregate stats over fresh listings |
| `POST` | `/api/refresh` | Force an immediate eBay poll (returns an HTML toast) |
| `POST` | `/api/test-discord` | Send a test message (`webhook_url` form field overrides the global one) |
| `GET` | `/health` | Health check + `ebay_configured` / `last_poll_at` |

## Data

SQLite (`romaleos.db`, WAL mode), created and migrated automatically on startup:

- `listings` — cached eBay items (`first_seen` / `last_seen` drive freshness)
- `watches` — user alert rules (`webhook_url` optionally overrides the Discord channel)
- `notifications` — one row per alert sent (dedupes repeat pings)
- `meta` — key/value (`last_poll_at`, `last_poll_count`)

`romaleos.db` is gitignored. `python seed.py` loads a small sample dataset into an
empty database for local UI work.

## Replit Deployment

1. Create a new Python Repl from this repo.
2. Add Secrets: `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, and optionally `DISCORD_WEBHOOK_URL`.
3. Run — the `Start application` workflow serves the preview on port `5000`.

The Replit config (`.replit`) uses a workspace-local `.venv/` that survives container
resets. Packages are auto-installed on boot via `install = ".venv/bin/pip install -r requirements.txt"`.
A workspace-local `.pip/pip.conf` overrides Replit's system pip config (which forces
user installs that don't always persist) so the venv stays clean and reliable.

See [`replit.md`](replit.md) for Replit-specific notes and [`scripts/hermes-persistence.md`](scripts/hermes-persistence.md) for Hermes agent persistence notes.

## License

MIT — BUTTERGANG
