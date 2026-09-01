"""ROMALEOS 2 — FastAPI web application."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import get_conn, get_meta, init_db
from app.ebay_client import get_client, parse_listing
from app.scheduler import poll_listings, start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# Throttle page-load-triggered live searches per (query, sort) to protect
# the eBay Browse API daily budget. Value is a monotonic timestamp.
_last_live_search: dict[str, float] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.ebay_configured:
        conn = get_conn()
        # Poll on startup so the dashboard has a fresh, trustworthy "as of"
        # time immediately — unless a poll already ran in the last 5 minutes
        # (guards against a crash-loop hammering the API).
        recent_poll = conn.execute(
            "SELECT 1 FROM meta WHERE key = 'last_poll_at' "
            "AND value >= datetime('now', '-5 minutes')"
        ).fetchone()
        conn.close()
        start_scheduler(run_now=not recent_poll)
        logger.info("eBay credentials found — scheduler started (run_now=%s)", not recent_poll)
    else:
        logger.warning("eBay credentials not configured — set EBAY_CLIENT_ID/CLIENT_SECRET")
    yield
    stop_scheduler()


app = FastAPI(title="ROMALEOS 2 Tracker", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── Helpers ────────────────────────────────────────────────────────────

def _parse_optional_price(value: str | float | None) -> float | None:
    """Convert an optional form/query price, treating blank input as unset."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


_SORT_SQL = {
    "newlyListed": "COALESCE(listed_at, first_seen) DESC",
    "price": "price ASC",
    "-price": "price DESC",
    "endingSoonest": "CASE WHEN listing_ends IS NULL OR listing_ends = '' THEN 1 ELSE 0 END, listing_ends ASC",
}


def _relative_age(iso_ts: str | None) -> str:
    """Human 'listed 3h ago' from an ISO timestamp; '' if unparseable."""
    if not iso_ts:
        return ""
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ts
    secs = int(delta.total_seconds())
    if secs < 0:
        return "just now"
    if secs < 3600:
        return f"{max(secs // 60, 1)}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def _decorate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add derived display fields (relative age, 'new' flag)."""
    now = datetime.now(timezone.utc)
    for r in rows:
        r["age_label"] = _relative_age(r.get("listed_at"))
        first_seen = r.get("first_seen")
        r["is_new"] = False
        if first_seen:
            try:
                fs = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
                if fs.tzinfo is None:
                    fs = fs.replace(tzinfo=timezone.utc)
                r["is_new"] = (now - fs).total_seconds() < 24 * 3600
            except ValueError:
                pass
    return rows


def _refresh_live(conn, query: str, sort: str, limit: int) -> None:
    """Pull fresh results from eBay into the DB, throttled per query+sort."""
    if not settings.ebay_configured:
        return
    key = f"{query}|{sort}"
    now = time.monotonic()
    if now - _last_live_search.get(key, 0.0) < settings.live_search_cache_seconds:
        return
    try:
        items = get_client().search(query, limit=limit, sort=sort)
    except Exception as e:  # noqa: BLE001
        logger.error("eBay live search failed: %s", e)
        return
    _last_live_search[key] = now
    for item in items:
        parsed = parse_listing(item)
        if not parsed["item_id"]:
            continue
        conn.execute(
            """INSERT INTO listings (item_id, title, price, currency, condition,
               item_url, image_url, shipping, accepts_offer, category,
               listed_at, listing_ends, seller, size, first_seen, last_seen, is_active)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'),1)
               ON CONFLICT(item_id) DO UPDATE SET
               title=excluded.title, price=excluded.price, condition=excluded.condition,
               image_url=excluded.image_url, shipping=excluded.shipping,
               accepts_offer=excluded.accepts_offer, last_seen=excluded.last_seen,
               is_active=1""",
            tuple(parsed[k] for k in [
                "item_id", "title", "price", "currency", "condition",
                "item_url", "image_url", "shipping", "accepts_offer",
                "category", "listed_at", "listing_ends", "seller", "size",
            ]),
        )
    conn.commit()


def _get_listings(
    search: str = "",
    sort: str = "newlyListed",
    price_min: float | None = None,
    price_max: float | None = None,
    condition: str = "",
    size_filter: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return listings from the local DB, opportunistically refreshed from eBay.

    Only listings seen within ``listing_stale_hours`` are returned, per the
    eBay API License Agreement's data-freshness requirement.
    """
    conn = get_conn()
    # Always scope live searches to the base product query so a free-text
    # search refines Romaleos 2 results rather than replacing them.
    query = f"{settings.default_search_query} {search}".strip() if search else settings.default_search_query
    if search or sort != "newlyListed":
        _refresh_live(conn, query, sort, limit)

    sql = [
        "SELECT * FROM listings WHERE is_active = 1",
        "AND last_seen >= datetime('now', ?)",
    ]
    params: list[Any] = [f"-{settings.listing_stale_hours} hours"]
    if search:
        sql.append("AND title LIKE ?")
        params.append(f"%{search}%")
    if price_min is not None:
        sql.append("AND price >= ?")
        params.append(price_min)
    if price_max is not None:
        sql.append("AND price <= ?")
        params.append(price_max)
    if condition:
        sql.append("AND condition = ?")
        params.append(condition)
    if size_filter:
        sql.append("AND size = ?")
        params.append(size_filter)
    sql.append(f"ORDER BY {_SORT_SQL.get(sort, _SORT_SQL['newlyListed'])} LIMIT ?")
    params.append(limit)

    rows = [dict(r) for r in conn.execute(" ".join(sql), params).fetchall()]
    conn.close()
    return _decorate(rows)


# ── Routes ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    search: str = Query(""),
    sort: str = Query("newlyListed"),
    price_min: str = Query(""),
    price_max: str = Query(""),
    condition: str = Query(""),
    size: str = Query(""),
) -> HTMLResponse:
    parsed_price_min = _parse_optional_price(price_min)
    parsed_price_max = _parse_optional_price(price_max)
    listings = await run_in_threadpool(
        _get_listings, search, sort, parsed_price_min, parsed_price_max, condition, size,
    )

    conn = get_conn()
    fresh_clause = "is_active=1 AND last_seen >= datetime('now', ?)"
    fresh_param = (f"-{settings.listing_stale_hours} hours",)
    sizes = [
        r["size"] for r in conn.execute(
            f"SELECT DISTINCT size FROM listings WHERE {fresh_clause} AND size IS NOT NULL "
            "ORDER BY CAST(size AS REAL)", fresh_param
        ).fetchall()
    ]
    conditions = [
        r["condition"] for r in conn.execute(
            f"SELECT DISTINCT condition FROM listings WHERE {fresh_clause} AND condition IS NOT NULL "
            "ORDER BY condition", fresh_param
        ).fetchall()
    ]
    total_fresh = conn.execute(
        f"SELECT COUNT(*) c FROM listings WHERE {fresh_clause}", fresh_param
    ).fetchone()["c"]
    # "As of" = the most recently seen listing; always present once any data
    # exists, unlike last_poll_at which only lands after a poll completes.
    as_of = conn.execute(
        "SELECT MAX(last_seen) m FROM listings WHERE is_active = 1"
    ).fetchone()["m"]
    conn.close()

    prices = [l["price"] for l in listings if l.get("price")]
    avg_price = round(sum(prices) / len(prices), 2) if prices else 0
    min_price = round(min(prices), 2) if prices else 0
    max_price = round(max(prices), 2) if prices else 0

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "listings": listings,
            "shown_count": len(listings),
            "total_fresh": total_fresh,
            "avg_price": avg_price,
            "min_price": min_price,
            "max_price": max_price,
            "search": search,
            "sort": sort,
            "price_min": price_min,
            "price_max": price_max,
            "condition": condition,
            "size_filter": size,
            "sizes": sizes,
            "conditions": conditions,
            "has_credentials": bool(settings.ebay_client_id),
            "ebay_configured": settings.ebay_configured,
            "as_of": as_of,
            "as_of_age": _relative_age(as_of),
            "syncing": settings.ebay_configured and total_fresh == 0,
            "stale_hours": int(settings.listing_stale_hours),
        },
    )


@app.get("/watches", response_class=HTMLResponse)
async def watches_page(request: Request) -> HTMLResponse:
    conn = get_conn()
    rows = conn.execute(
        """SELECT w.*, (SELECT COUNT(*) FROM notifications n WHERE n.watch_id = w.id) as alerts_sent
           FROM watches w ORDER BY w.created_at DESC"""
    ).fetchall()
    conn.close()
    return templates.TemplateResponse(
        request, "watches.html",
        {"request": request, "watches": rows, "ebay_configured": settings.ebay_configured},
    )


@app.post("/watches/add")
async def add_watch(
    label: str = Form(""),
    size_exact: str = Form(""),
    min_size: str = Form(""),
    max_size: str = Form(""),
    max_price: str = Form(""),
    min_price: str = Form(""),
    webhook_url: str = Form(""),
):
    conn = get_conn()
    conn.execute(
        "INSERT INTO watches (label, size_exact, min_size, max_size, max_price, min_price, webhook_url) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            label.strip(), size_exact.strip(), min_size.strip(), max_size.strip(),
            _parse_optional_price(max_price), _parse_optional_price(min_price),
            webhook_url.strip() or None,
        ),
    )
    conn.commit()
    conn.close()
    return RedirectResponse("/watches", status_code=303)


@app.post("/watches/{watch_id}/toggle")
async def toggle_watch(watch_id: int):
    conn = get_conn()
    changed = conn.execute(
        "UPDATE watches SET active = CASE WHEN active THEN 0 ELSE 1 END WHERE id = ?",
        (watch_id,),
    ).rowcount
    conn.commit()
    conn.close()
    if not changed:
        raise HTTPException(status_code=404, detail="Watch not found")
    return RedirectResponse("/watches", status_code=303)


@app.post("/watches/{watch_id}/delete")
async def delete_watch(watch_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM notifications WHERE watch_id = ?", (watch_id,))
    changed = conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,)).rowcount
    conn.commit()
    conn.close()
    if not changed:
        raise HTTPException(status_code=404, detail="Watch not found")
    return RedirectResponse("/watches", status_code=303)


@app.get("/api/listings")
async def api_listings(
    search: str = Query(""),
    sort: str = Query("newlyListed"),
    limit: int = Query(50, ge=1, le=200),
):
    """JSON endpoint for programmatic access."""
    listings = await run_in_threadpool(
        _get_listings, search, sort, None, None, "", "", limit,
    )
    conn = get_conn()
    as_of = conn.execute(
        "SELECT MAX(last_seen) m FROM listings WHERE is_active = 1"
    ).fetchone()["m"]
    last_poll_at = get_meta(conn, "last_poll_at")
    conn.close()
    return {
        "count": len(listings),
        "as_of": as_of,
        "last_poll_at": last_poll_at,
        "max_age_hours": settings.listing_stale_hours,
        "listings": listings,
    }


@app.get("/api/stats")
async def api_stats():
    conn = get_conn()
    fresh = "is_active=1 AND last_seen >= datetime('now', ?)"
    p = (f"-{settings.listing_stale_hours} hours",)
    total = conn.execute(f"SELECT COUNT(*) c FROM listings WHERE {fresh}", p).fetchone()["c"]
    avg_price = conn.execute(f"SELECT AVG(price) x FROM listings WHERE {fresh}", p).fetchone()["x"] or 0
    min_price = conn.execute(f"SELECT MIN(price) x FROM listings WHERE {fresh}", p).fetchone()["x"] or 0
    max_price = conn.execute(f"SELECT MAX(price) x FROM listings WHERE {fresh}", p).fetchone()["x"] or 0
    watch_count = conn.execute("SELECT COUNT(*) c FROM watches WHERE active=1").fetchone()["c"]
    alerts_sent = conn.execute("SELECT COUNT(*) c FROM notifications").fetchone()["c"]
    as_of = conn.execute(
        "SELECT MAX(last_seen) m FROM listings WHERE is_active = 1"
    ).fetchone()["m"]
    last_poll_at = get_meta(conn, "last_poll_at")
    conn.close()
    return {
        "active_listings": total,
        "avg_price": round(avg_price, 2),
        "min_price": round(min_price, 2),
        "max_price": round(max_price, 2),
        "active_watches": watch_count,
        "alerts_sent": alerts_sent,
        "as_of": as_of,
        "last_poll_at": last_poll_at,
    }


@app.post("/api/refresh", response_class=HTMLResponse)
async def api_refresh():
    """Force a manual eBay poll."""
    if not settings.ebay_configured:
        return HTMLResponse(
            '<div class="toast error">❌ eBay API not configured — set EBAY_CLIENT_ID / EBAY_CLIENT_SECRET</div>',
            status_code=503,
        )
    try:
        result = await poll_listings()
        extra = f", {result['alerts']} alert(s) sent" if result.get("alerts") else ""
        return HTMLResponse(
            f'<div class="toast success">✅ Polled eBay — {result["processed"]} listings, '
            f'{result["purged"]} expired{extra}</div>'
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Manual refresh failed")
        return HTMLResponse(
            f'<div class="toast error">❌ Poll failed: {e}</div>', status_code=502
        )


@app.get("/health")
async def health():
    conn = get_conn()
    last_poll_at = get_meta(conn, "last_poll_at")
    conn.close()
    return {
        "status": "ok",
        "app": "romaleos-2-tracker",
        "version": "1.0.0",
        "ebay_configured": settings.ebay_configured,
        "discord_configured": bool(settings.discord_webhook_url),
        "last_poll_at": last_poll_at,
    }


@app.post("/api/test-discord")
async def test_discord(webhook_url: str = Form("")):
    """Send a test message. Body param ``webhook_url`` overrides the global one."""
    from app.discord import send_test_notification

    url = webhook_url.strip() or settings.discord_webhook_url
    if not url:
        return JSONResponse(
            {"status": "error", "message": "No webhook URL — set DISCORD_WEBHOOK_URL or pass webhook_url"},
            status_code=400,
        )
    ok = await run_in_threadpool(send_test_notification, url)
    if ok:
        return {"status": "ok", "message": "Test message sent — check your Discord channel"}
    return JSONResponse(
        {"status": "error", "message": "Discord rejected the webhook — double-check the URL"},
        status_code=502,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
