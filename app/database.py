"""SQLite database setup and helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "romaleos.db"


def get_conn() -> sqlite3.Connection:
    """Return a connection with row-factory enabled."""
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS listings (
            item_id      TEXT PRIMARY KEY,
            title        TEXT NOT NULL,
            price        REAL NOT NULL,
            currency     TEXT NOT NULL DEFAULT 'USD',
            condition    TEXT,
            item_url     TEXT,
            image_url    TEXT,
            shipping     REAL DEFAULT 0,
            accepts_offer INTEGER DEFAULT 0,
            category     TEXT,
            listed_at    TEXT,
            listing_ends TEXT,
            seller       TEXT,
            size         TEXT,
            first_seen   TEXT DEFAULT (datetime('now')),
            last_seen    TEXT DEFAULT (datetime('now')),
            is_active    INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS watches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            label       TEXT DEFAULT '',
            min_size    TEXT,
            max_size    TEXT,
            max_price   REAL,
            min_price   REAL DEFAULT 0,
            size_exact  TEXT,
            webhook_url TEXT,
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_id    INTEGER REFERENCES watches(id),
            listing_id  TEXT REFERENCES listings(item_id),
            sent_at     TEXT DEFAULT (datetime('now')),
            method      TEXT DEFAULT 'discord'
        );

        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price);
        CREATE INDEX IF NOT EXISTS idx_listings_active ON listings(is_active);
        CREATE INDEX IF NOT EXISTS idx_listings_size ON listings(size);
        CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen);
        CREATE INDEX IF NOT EXISTS idx_watches_active ON watches(active);
    """)
    # Backfill first_seen for rows created before the column existed.  Use the
    # eBay listing-creation date when known so migrated rows don't all look
    # brand new; fall back to last_seen.
    listing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(listings)")}
    if "first_seen" not in listing_cols:
        conn.execute("ALTER TABLE listings ADD COLUMN first_seen TEXT")
    conn.execute(
        "UPDATE listings SET first_seen = COALESCE(NULLIF(listed_at, ''), last_seen) "
        "WHERE first_seen IS NULL OR first_seen = ''"
    )
    # Per-watch Discord webhook override (added later; NULL = use the global one).
    watch_cols = {r["name"] for r in conn.execute("PRAGMA table_info(watches)")}
    if "webhook_url" not in watch_cols:
        conn.execute("ALTER TABLE watches ADD COLUMN webhook_url TEXT")
    conn.commit()
    conn.close()


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def enforce_retention(conn: sqlite3.Connection, stale_hours: float, purge_hours: float) -> tuple[int, int]:
    """Apply the eBay data-freshness rules.

    - Listings not re-seen within ``stale_hours`` are marked inactive so
      they stop showing on the dashboard (data must be < 6h old).
    - Listings not re-seen within ``purge_hours`` are deleted outright
      (content for items no longer available must be removed).

    Returns ``(deactivated, purged)`` counts.
    """
    deactivated = conn.execute(
        "UPDATE listings SET is_active = 0 "
        "WHERE is_active = 1 AND last_seen < datetime('now', ?)",
        (f"-{stale_hours} hours",),
    ).rowcount
    # Detach notifications first so the FK constraint doesn't block deletes.
    conn.execute(
        "DELETE FROM notifications WHERE listing_id IN "
        "(SELECT item_id FROM listings WHERE last_seen < datetime('now', ?))",
        (f"-{purge_hours} hours",),
    )
    purged = conn.execute(
        "DELETE FROM listings WHERE last_seen < datetime('now', ?)",
        (f"-{purge_hours} hours",),
    ).rowcount
    return deactivated, purged
