# ROMALEOS 2 Tracker on Replit

## Run

The project runs as a single FastAPI web workflow. The Replit config (`.replit`) pins
the run command to the workspace `.venv/` so it always picks up the installed packages:

```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 5000
```

The `install` hook in `.replit` runs `.venv/bin/pip install -r requirements.txt` on boot
so packages are restored automatically if the venv is ever missing.

A workspace-local `.pip/pip.conf` overrides Replit's system pip config (which forces
`--user` installs). Without it, `pip install` inside a venv fails with
`Can not perform a '--user' install`. The local config lives at `.pip/pip.conf` in the
workspace and is gitignored (not portable to other machines).

The SQLite schema is created and migrated automatically on startup — no manual step.

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

`PORT` is set to `5000` in `.replit` `[env]`. `SESSION_SECRET` is available in the
workspace; the app reads `SECRET_KEY` (currently unused — reserved for future
session support).

## Persistence on Replit

Replit containers recycle periodically. Here's what stays and what doesn't:

| Persists ✅ | Doesn't persist ❌ |
|---|---|
| `/home/runner/workspace/.venv/` — installed packages | Running processes |
| `/home/runner/workspace/.pip/pip.conf` — pip override | Shell session state (`.bashrc` etc.) |
| `/home/runner/workspace/.replit` — Replit config | |
| `/home/runner/workspace/romaleos.db` — app data (gitignored) | |
| `/home/runner/workspace/.env` — secrets (gitignored) | |
| `/home/runner/workspace/.hermes/` — Hermes agent (see `scripts/hermes-persistence.md`) | |
| `/home/runner/workspace/.gitignore`, source files, committed config | |

The key point: everything important lives in `/home/runner/workspace/`. The `.venv/`
directory is committed to gitignore but still sits in the workspace — Replit persists
the directory itself; it just won't show up in `git push`.

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
