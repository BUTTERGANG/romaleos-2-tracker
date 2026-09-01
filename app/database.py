"""SQLite database setup and helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "romaleos.db"


def get_conn() -> sqlite3.Connection:
    """Return a connection with row-factory enabled."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
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

        CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price);
        CREATE INDEX IF NOT EXISTS idx_listings_active ON listings(is_active);
        CREATE INDEX IF NOT EXISTS idx_listings_size ON listings(size);
        CREATE INDEX IF NOT EXISTS idx_watches_active ON watches(active);
    """)
    conn.commit()
    conn.close()