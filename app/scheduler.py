"""Background scheduler — periodically polls eBay for new listings and checks watches."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import enforce_retention, get_conn, set_meta
from app.discord import send_matches
from app.ebay_client import get_client, parse_listing

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _poll_sync() -> dict[str, int]:
    """Blocking poll: fetch listings, upsert, check watches, enforce retention.

    Runs in a worker thread so the eBay HTTP calls and SQLite writes never
    block the event loop.
    """
    client = get_client()
    try:
        items = client.search_romaleos2(limit=50)
    except Exception as e:
        logger.error("eBay search failed: %s", e)
        raise

    conn = get_conn()
    matches: list[dict] = []
    try:
        watch_rows = conn.execute(
            "SELECT id, label, min_size, max_size, max_price, min_price, size_exact, webhook_url "
            "FROM watches WHERE active = 1"
        ).fetchall()

        for item in items:
            listing = parse_listing(item)
            item_id = listing["item_id"]
            if not item_id:
                continue

            conn.execute(
                """INSERT INTO listings (item_id, title, price, currency, condition,
                   item_url, image_url, shipping, accepts_offer, category,
                   listed_at, listing_ends, seller, size, first_seen, last_seen, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 1)
                   ON CONFLICT(item_id) DO UPDATE SET
                   title = excluded.title, price = excluded.price,
                   condition = excluded.condition, image_url = excluded.image_url,
                   last_seen = excluded.last_seen, is_active = 1,
                   shipping = excluded.shipping, accepts_offer = excluded.accepts_offer""",
                (
                    item_id, listing["title"], listing["price"], listing["currency"],
                    listing["condition"], listing["item_url"], listing["image_url"],
                    listing["shipping"], listing["accepts_offer"], listing["category"],
                    listing["listed_at"], listing["listing_ends"], listing["seller"],
                    listing["size"],
                ),
            )
            matches.extend(_match_watches(conn, watch_rows, listing))

        # Deliver alerts in batches, then record only what actually went out
        # (undelivered matches retry on the next poll).
        sent = 0
        if matches:
            delivered = send_matches(matches)
            for m in matches:
                if (m["watch_id"], m["listing_id"]) in delivered:
                    conn.execute(
                        "INSERT INTO notifications (watch_id, listing_id, method) VALUES (?, ?, 'discord')",
                        (m["watch_id"], m["listing_id"]),
                    )
            sent = len(delivered)
            if sent < len(matches):
                logger.warning("Discord: %d/%d alerts delivered this poll", sent, len(matches))

        deactivated, purged = enforce_retention(
            conn, settings.listing_stale_hours, settings.listing_purge_hours
        )
        set_meta(conn, "last_poll_at", _utcnow())
        set_meta(conn, "last_poll_count", str(len(items)))
        conn.commit()
    finally:
        conn.close()

    if deactivated or purged:
        logger.info("Retention: %d deactivated, %d purged", deactivated, purged)
    logger.info("Polled eBay: %d listings processed, %d alerts sent", len(items), sent)
    return {"processed": len(items), "deactivated": deactivated, "purged": purged, "alerts": sent}


async def poll_listings() -> dict[str, int]:
    """Async entry point — offloads the blocking work to a thread."""
    return await run_in_threadpool(_poll_sync)


def _utcnow() -> str:
    """UTC now in SQLite's ``datetime()`` text format for safe string compares."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _match_watches(conn, watch_rows, listing: dict) -> list[dict]:
    """Return the (not-yet-notified) watch matches for one listing."""
    price = listing["price"]
    size = listing.get("size")
    out: list[dict] = []

    for row in watch_rows:
        watch_id = row["id"]

        if row["max_price"] is not None and price > row["max_price"]:
            continue
        if row["min_price"] is not None and price < row["min_price"]:
            continue

        if row["size_exact"] and size and size != row["size_exact"]:
            continue
        if row["min_size"] and size and _size_cmp(size, row["min_size"]) < 0:
            continue
        if row["max_size"] and size and _size_cmp(size, row["max_size"]) > 0:
            continue

        already = conn.execute(
            "SELECT 1 FROM notifications WHERE watch_id = ? AND listing_id = ?",
            (watch_id, listing["item_id"]),
        ).fetchone()
        if already:
            continue

        out.append({
            "watch_id": watch_id,
            "listing_id": listing["item_id"],
            "listing": listing,
            "watch_label": row["label"] or f"Watch #{watch_id}",
            "webhook_url": row["webhook_url"],
        })
    return out


def _size_cmp(a: str | None, b: str | None) -> int:
    """Compare shoe size strings as floats, fallback to string compare."""
    try:
        return -1 if float(a or 0) < float(b or 0) else 1 if float(a or 0) > float(b or 0) else 0
    except (ValueError, TypeError):
        return -1 if (a or "") < (b or "") else 1 if (a or "") > (b or "") else 0


def start_scheduler(run_now: bool = False) -> None:
    """Start the background poller.

    ``run_now`` schedules an immediate first poll (used when the DB has no
    fresh listings yet) so a new deploy isn't blank until the first interval.
    """
    interval = settings.poll_interval_minutes
    kwargs: dict = {}
    if run_now:
        from datetime import datetime, timezone

        kwargs["next_run_time"] = datetime.now(timezone.utc)
    scheduler.add_job(
        poll_listings, "interval", minutes=interval, id="poll_ebay",
        max_instances=1, coalesce=True, replace_existing=True, **kwargs,
    )
    scheduler.start()
    logger.info("Scheduler started — polling every %d minutes (run_now=%s)", interval, run_now)


def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
