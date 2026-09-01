# ROMALEOS 2 Tracker on Replit

## Run

The project runs as a single FastAPI web workflow:

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 5000
```

The Replit workflow is named `Start application` and serves the browser preview
on port `5000`. The SQLite schema is created and migrated automatically on
startup — no manual step.

## Environment

The app runs without credentials but only serves whatever is already cached in
`romaleos.db` (live search and background polling are disabled). To enable live
eBay data, add these Secrets:

- `EBAY_CLIENT_ID` — eBay Developer App ID
- `EBAY_CLIENT_SECRET` — eBay Developer App Secret

The app also accepts eBay's dashboard names `APP_ID` and `CERT_ID` as aliases.
`DEV_ID` is not used by this OAuth2 Browse API client.

Optional Secrets:

| Secret | Default | Purpose |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | — | Discord webhook for watch alerts (Server Settings → Integrations → Webhooks). Per-watch overrides are set in the UI. |
| `POLL_INTERVAL_MINUTES` | `30` | Background poll frequency |
| `SEARCH_QUERY` | `Nike Romaleos 2` | Base search query |
| `EBAY_MARKETPLACE` | `EBAY_US` | eBay marketplace ID |
| `LISTING_STALE_HOURS` | `6` | Hide listings not re-seen within N hours |
| `LISTING_PURGE_HOURS` | `24` | Delete listings not re-seen within N hours |
| `LIVE_SEARCH_CACHE_SECONDS` | `120` | Throttle for page-load-triggered eBay calls |

`PORT` is set to `5000` by the workflow. `SESSION_SECRET` is available in the
workspace; the app reads `SECRET_KEY` (currently unused — reserved for future
session support).

## Behaviour notes

- **Startup poll** — on boot the scheduler runs one poll immediately (unless a
  poll completed in the last 5 minutes), so the dashboard has fresh data right
  away instead of waiting up to 30 minutes.
- **Freshness** — the dashboard only shows listings seen within
  `LISTING_STALE_HOURS` and displays an "as of" time. Older rows are hidden, then
  deleted after `LISTING_PURGE_HOURS`, to satisfy eBay's API License Agreement.
- **Rate limiting** — background polling plus throttled, cached page-load searches
  keep usage well under the Browse API's 5,000 calls/day.
- **Discord** — an incoming webhook (not a bot). Alerts are batched (≤10 embeds
  per request), retried on `429`/`5xx`, and de-duped per `(watch, listing)`.
- **Persistence** — `romaleos.db` lives in the repo root (gitignored) and
  survives restarts. Deleting it triggers a fresh sync on next boot.

## Useful endpoints

- `/` — listings dashboard
- `/watches` — manage price and size watches
- `/health` — health check (`ebay_configured`, `last_poll_at`)
- `/api/listings` — listings JSON (`as_of`, `last_poll_at`)
- `/api/stats` — aggregate stats
- `POST /api/refresh` — force an immediate poll
- `POST /api/test-discord` — send a test webhook message
