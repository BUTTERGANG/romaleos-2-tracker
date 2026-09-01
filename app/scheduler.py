"""Background scheduler — periodically polls eBay for new listings and checks watches."""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import get_conn
from app.discord import send_notification
from app.ebay_client import get_client, parse_listing

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def poll_listings() -> None:
    """Fetch latest Romaleos 2 listings and check against watches."""
    client = get_client()
    try:
        items = client.search_romaleos2(limit=50)
    except Exception as e:
        logger.error("eBay search failed: %s", e)
        return

    conn = get_conn()
    new_count = 0

    for item in items:
        listing = parse_listing(item)
        item_id = listing["item_id"]
        if not item_id:
            continue

        # Upsert listing
        conn.execute(
            """INSERT INTO listings (item_id, title, price, currency, condition,
               item_url, image_url, shipping, accepts_offer, category,
               listed_at, listing_ends, seller, size, last_seen, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 1)
               ON CONFLICT(item_id) DO UPDATE SET
               price = excluded.price, last_seen = excluded.last_seen,
               is_active = 1, shipping = excluded.shipping,
               accepts_offer = excluded.accepts_offer""",
            (
                item_id, listing["title"], listing["price"], listing["currency"],
                listing["condition"], listing["item_url"], listing["image_url"],
                listing["shipping"], listing["accepts_offer"], listing["category"],
                listing["listed_at"], listing["listing_ends"], listing["seller"],
                listing["size"],
            ),
        )

        # Check watches
        _check_watches(conn, listing)

    conn.commit()
    conn.close()
    logger.info("Polled eBay: %d listings processed", len(items))


def _check_watches(conn, listing: dict) -> None:
    """Check if a listing matches any active watch and send notification."""
    rows = conn.execute(
        "SELECT id, label, min_size, max_size, max_price, min_price, size_exact "
        "FROM watches WHERE active = 1"
    ).fetchall()

    price = listing["price"]
    size = listing.get("size")

    for row in rows:
        watch_id = row["id"]

        # Price filter
        if row["max_price"] is not None and price > row["max_price"]:
            continue
        if row["min_price"] is not None and price < row["min_price"]:
            continue

        # Size filter
        if row["size_exact"] and size and size != row["size_exact"]:
            continue
        if row["min_size"] and size and _size_cmp(size, row["min_size"]) < 0:
            continue
        if row["max_size"] and size and _size_cmp(size, row["max_size"]) > 0:
            continue

        # Check already notified
        already = conn.execute(
            "SELECT 1 FROM notifications WHERE watch_id = ? AND listing_id = ?",
            (watch_id, listing["item_id"]),
        ).fetchone()
        if already:
            continue

        # Send notification
        label = row["label"] or f"Watch #{watch_id}"
        ok = send_notification(listing, watch_label=label)
        if ok:
            conn.execute(
                "INSERT INTO notifications (watch_id, listing_id, method) VALUES (?, ?, 'discord')",
                (watch_id, listing["item_id"]),
            )
            logger.info("Notification sent for watch #%d, listing %s", watch_id, listing["item_id"])


def _size_cmp(a: str | None, b: str | None) -> int:
    """Compare shoe size strings as floats, fallback to string compare."""
    try:
        return -1 if float(a or 0) < float(b or 0) else 1 if float(a or 0) > float(b or 0) else 0
    except (ValueError, TypeError):
        return -1 if (a or "") < (b or "") else 1 if (a or "") > (b or "") else 0


def start_scheduler() -> None:
    """Start the background poller."""
    interval = settings.poll_interval_minutes
    scheduler.add_job(poll_listings, "interval", minutes=interval, id="poll_ebay")
    scheduler.start()
    logger.info("Scheduler started — polling every %d minutes", interval)


def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)