"""ROMALEOS 2 — FastAPI web application."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import settings
from app.database import get_conn, init_db
from app.discord import send_notification
from app.ebay_client import get_client, parse_listing
from app.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="ROMALEOS 2 Tracker", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── Lifecycle ──────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    if settings.ebay_client_id and settings.ebay_client_secret:
        start_scheduler()
        logger.info("eBay credentials found — scheduler started")
    else:
        logger.warning("eBay credentials not configured — set EBAY_CLIENT_ID/CLIENT_SECRET in .env")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    stop_scheduler()


# ── Helpers ────────────────────────────────────────────────────────────

def _get_listings(
    search: str = "",
    sort: str = "newlyListed",
    price_min: float | None = None,
    price_max: float | None = None,
    condition: str = "",
    size_filter: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get listings — either from eBay API or from local DB."""
    conn = get_conn()
    query = search or settings.default_search_query
    page = 1 if search or sort != "newlyListed" else None

    results = []
    if page is not None:
        # Live search
        try:
            client = get_client()
            items = client.search(query, limit=limit, sort=sort)
            for item in items:
                parsed = parse_listing(item)
                # Upsert into DB
                conn.execute(
                    """INSERT INTO listings (item_id, title, price, currency, condition,
                       item_url, image_url, shipping, accepts_offer, category,
                       listed_at, listing_ends, seller, size, last_seen, is_active)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),1)
                       ON CONFLICT(item_id) DO UPDATE SET
                       price=excluded.price, last_seen=excluded.last_seen,
                       is_active=1""",
                    tuple(parsed[k] for k in [
                        "item_id", "title", "price", "currency", "condition",
                        "item_url", "image_url", "shipping", "accepts_offer",
                        "category", "listed_at", "listing_ends", "seller", "size",
                    ]),
                )
                results.append(parsed)
            conn.commit()
        except Exception as e:
            logger.error("eBay search failed: %s", e)
            # Fall through to cached

    if not results:
        # Cached results
        sql = "SELECT * FROM listings WHERE is_active = 1"
        params = []
        if price_min is not None:
            sql += " AND price >= ?"
            params.append(price_min)
        if price_max is not None:
            sql += " AND price <= ?"
            params.append(price_max)
        if condition:
            sql += " AND condition = ?"
            params.append(condition)
        if size_filter:
            sql += " AND size = ?"
            params.append(size_filter)
        sql += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        results = [dict(r) for r in rows]

    conn.close()
    return results


# ── Routes ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    search: str = Query(""),
    sort: str = Query("newlyListed"),
    price_min: float | None = Query(None),
    price_max: float | None = Query(None),
    condition: str = Query(""),
    size: str = Query(""),
) -> HTMLResponse:
    listings = _get_listings(
        search=search, sort=sort, price_min=price_min,
        price_max=price_max, condition=condition, size_filter=size,
    )
    # Gather unique sizes for filter dropdown
    conn = get_conn()
    sizes = [
        r["size"] for r in conn.execute(
            "SELECT DISTINCT size FROM listings WHERE is_active=1 AND size IS NOT NULL ORDER BY size"
        ).fetchall()
    ]
    conditions = [
        r["condition"] for r in conn.execute(
            "SELECT DISTINCT condition FROM listings WHERE is_active=1 AND condition IS NOT NULL ORDER BY condition"
        ).fetchall()
    ]
    conn.close()

    # Stats
    unique_items = len(set(l["item_id"] for l in listings)) if listings else 0
    avg_price = round(sum(l["price"] for l in listings) / len(listings), 2) if listings else 0
    min_price = round(min(l["price"] for l in listings), 2) if listings else 0
    max_price = round(max(l["price"] for l in listings), 2) if listings else 0

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "listings": listings,
            "unique_items": unique_items,
            "avg_price": avg_price,
            "min_price": min_price,
            "max_price": max_price,
            "search": search,
            "sort": sort,
            "price_min": price_min or "",
            "price_max": price_max or "",
            "condition": condition,
            "size_filter": size,
            "sizes": sizes,
            "conditions": conditions,
            "has_credentials": bool(settings.ebay_client_id),
            "ebay_configured": settings.ebay_client_id and settings.ebay_client_secret,
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
    return templates.TemplateResponse(request, "watches.html", {"request": request, "watches": rows})


@app.post("/watches/add")
async def add_watch(
    label: str = Form(""),
    size_exact: str = Form(""),
    min_size: str = Form(""),
    max_size: str = Form(""),
    max_price: float = Form(0),
    min_price: float = Form(0),
):
    conn = get_conn()
    conn.execute(
        "INSERT INTO watches (label, size_exact, min_size, max_size, max_price, min_price) VALUES (?,?,?,?,?,?)",
        (label, size_exact, min_size, max_size, max_price or None, min_price or None),
    )
    conn.commit()
    conn.close()
    return RedirectResponse("/watches", status_code=303)


@app.post("/watches/{watch_id}/toggle")
async def toggle_watch(watch_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE watches SET active = CASE WHEN active THEN 0 ELSE 1 END WHERE id = ?",
        (watch_id,),
    )
    conn.commit()
    conn.close()
    return RedirectResponse("/watches", status_code=303)


@app.post("/watches/{watch_id}/delete")
async def delete_watch(watch_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM notifications WHERE watch_id = ?", (watch_id,))
    conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/watches", status_code=303)


@app.get("/api/listings")
async def api_listings(
    search: str = Query(""),
    sort: str = Query("newlyListed"),
    limit: int = Query(50),
):
    """JSON endpoint for programmatic access."""
    listings = _get_listings(search=search, sort=sort, limit=limit)
    return {"count": len(listings), "listings": listings}


@app.get("/api/stats")
async def api_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) as c FROM listings WHERE is_active=1").fetchone()["c"]
    avg_price = conn.execute("SELECT AVG(price) as p FROM listings WHERE is_active=1").fetchone()["p"] or 0
    min_price = conn.execute("SELECT MIN(price) as p FROM listings WHERE is_active=1").fetchone()["p"] or 0
    max_price = conn.execute("SELECT MAX(price) as p FROM listings WHERE is_active=1").fetchone()["p"] or 0
    watch_count = conn.execute("SELECT COUNT(*) as c FROM watches WHERE active=1").fetchone()["c"]
    alerts_sent = conn.execute("SELECT COUNT(*) as c FROM notifications").fetchone()["c"]
    conn.close()
    return {
        "active_listings": total,
        "avg_price": round(avg_price, 2),
        "min_price": round(min_price, 2),
        "max_price": round(max_price, 2),
        "active_watches": watch_count,
        "alerts_sent": alerts_sent,
    }


@app.post("/api/refresh", response_class=HTMLResponse)
async def api_refresh(request: Request):
    """Force a manual eBay poll."""
    from app.scheduler import poll_listings
    try:
        await poll_listings()
        conn = get_conn()
        total = conn.execute("SELECT COUNT(*) as c FROM listings WHERE is_active=1").fetchone()["c"]
        conn.close()
        return HTMLResponse(
            f'<div class="toast success">✅ Polled eBay — {total} active listings in DB</div>'
        )
    except Exception as e:
        return HTMLResponse(
            f'<div class="toast error">❌ Poll failed: {e}</div>'
        )


@app.get("/health")
async def health():
    return {"status": "ok", "app": "romaleos-2-tracker", "version": "1.0.0"}


@app.post("/api/test-discord")
async def test_discord():
    from app.discord import send_test_notification
    ok = send_test_notification(settings.discord_webhook_url)
    if ok:
        return {"status": "ok", "message": "Test notification sent"}
    return {"status": "error", "message": "Discord webhook failed — check DISCORD_WEBHOOK_URL in .env"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)