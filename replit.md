# ROMALEOS 2 Tracker on Replit

## Run

The project runs as a single FastAPI web workflow:

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 5000
```

The Replit workflow is named `Start application` and serves the browser preview on port `5000`.

## Environment

The app starts without external credentials and displays an empty/cached listings view. To enable live eBay searches and background polling, add these Secrets:

- `EBAY_CLIENT_ID` — eBay Developer App ID
- `EBAY_CLIENT_SECRET` — eBay Developer App Secret

The app also accepts eBay's dashboard names `APP_ID` and `CERT_ID` as aliases. `DEV_ID` is not used by this OAuth2 Browse API client.

Optional:

- `DISCORD_WEBHOOK_URL` — Discord webhook used for alerts
- `POLL_INTERVAL_MINUTES` — polling interval in minutes (default `30`)
- `SEARCH_QUERY` — default search query (default `Nike Romaleos 2`)

`SESSION_SECRET` is already available in this workspace. The application currently reads `SECRET_KEY` for its app secret; set that separately if the app’s secret-key behavior is used.

## Useful endpoints

- `/` — listings dashboard
- `/watches` — manage price and size watches
- `/health` — health check
- `/api/listings` — listings JSON
- `/api/stats` — aggregate stats