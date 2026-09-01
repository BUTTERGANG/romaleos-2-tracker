"""Seed the database with sample Romaleos 2 listings for demo purposes."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "romaleos.db"

SAMPLE_LISTINGS = [
    {
        "item_id": "ROM-SAMPLE-001",
        "title": "Nike Romaleos 2 Weightlifting Shoes - US 10 - White/Red",
        "price": 149.99,
        "currency": "USD",
        "condition": "Used",
        "item_url": "https://www.ebay.com/itm/example1",
        "image_url": "",
        "shipping": 12.50,
        "accepts_offer": 1,
        "category": "Weightlifting Shoes",
        "listed_at": "2026-08-28T10:00:00Z",
        "listing_ends": "2026-09-15T10:00:00Z",
        "seller": "fitness_gear_shop",
        "size": "10",
        "is_active": 1,
    },
    {
        "item_id": "ROM-SAMPLE-002",
        "title": "Nike Romaleos 2 - Size US 9.5 - Excellent Condition",
        "price": 185.00,
        "currency": "USD",
        "condition": "Used - Like New",
        "item_url": "https://www.ebay.com/itm/example2",
        "image_url": "",
        "shipping": 0.00,
        "accepts_offer": 0,
        "category": "Weightlifting Shoes",
        "listed_at": "2026-08-25T14:30:00Z",
        "listing_ends": "2026-09-10T14:30:00Z",
        "seller": "lift_big_123",
        "size": "9.5",
        "is_active": 1,
    },
    {
        "item_id": "ROM-SAMPLE-003",
        "title": "Nike Romaleos 2 Weightlifting Shoe Sz US 11 - Black/Gold",
        "price": 210.00,
        "currency": "USD",
        "condition": "New with box",
        "item_url": "https://www.ebay.com/itm/example3",
        "image_url": "",
        "shipping": 0.00,
        "accepts_offer": 1,
        "category": "Weightlifting Shoes",
        "listed_at": "2026-08-30T09:00:00Z",
        "listing_ends": "2026-09-20T09:00:00Z",
        "seller": "iron_paradise",
        "size": "11",
        "is_active": 1,
    },
    {
        "item_id": "ROM-SAMPLE-004",
        "title": "Nike Romaleos 2 SE - Women US 7.5 - Rio Blue",
        "price": 129.99,
        "currency": "USD",
        "condition": "Used - Good",
        "item_url": "https://www.ebay.com/itm/example4",
        "image_url": "",
        "shipping": 8.99,
        "accepts_offer": 1,
        "category": "Weightlifting Shoes",
        "listed_at": "2026-08-22T11:00:00Z",
        "listing_ends": "2026-09-08T11:00:00Z",
        "seller": "gym_clearance",
        "size": "7.5",
        "is_active": 1,
    },
    {
        "item_id": "ROM-SAMPLE-005",
        "title": "Nike Romaleos 2 - US Men 10.5 - Volt Green - Rare",
        "price": 275.00,
        "currency": "USD",
        "condition": "Used - Very Good",
        "item_url": "https://www.ebay.com/itm/example5",
        "image_url": "",
        "shipping": 15.00,
        "accepts_offer": 0,
        "category": "Weightlifting Shoes",
        "listed_at": "2026-08-20T16:00:00Z",
        "listing_ends": "2026-09-05T16:00:00Z",
        "seller": "rare_kicks_finder",
        "size": "10.5",
        "is_active": 1,
    },
    {
        "item_id": "ROM-SAMPLE-006",
        "title": "Nike Romaleos 2 Size US 12 - White/Pink - Good Condition",
        "price": 160.00,
        "currency": "USD",
        "condition": "Used",
        "item_url": "https://www.ebay.com/itm/example6",
        "image_url": "",
        "shipping": 10.00,
        "accepts_offer": 1,
        "category": "Weightlifting Shoes",
        "listed_at": "2026-08-29T08:00:00Z",
        "listing_ends": "2026-09-12T08:00:00Z",
        "seller": "swole_patrol",
        "size": "12",
        "is_active": 1,
    },
    {
        "item_id": "ROM-SAMPLE-007",
        "title": "Nike Romaleos 2 - US 8 - Youth/Adult Small - Blue/White",
        "price": 99.99,
        "currency": "USD",
        "condition": "Used - Fair",
        "item_url": "https://www.ebay.com/itm/example7",
        "image_url": "",
        "shipping": 0.00,
        "accepts_offer": 1,
        "category": "Weightlifting Shoes",
        "listed_at": "2026-08-18T12:00:00Z",
        "listing_ends": "2026-09-02T12:00:00Z",
        "seller": "plate_racer",
        "size": "8",
        "is_active": 1,
    },
    {
        "item_id": "ROM-SAMPLE-008",
        "title": "NWOT Nike Romaleos 2 - Men US 9 - Black/White - Never Worn",
        "price": 199.99,
        "currency": "USD",
        "condition": "New without box",
        "item_url": "https://www.ebay.com/itm/example8",
        "image_url": "",
        "shipping": 0.00,
        "accepts_offer": 0,
        "category": "Weightlifting Shoes",
        "listed_at": "2026-08-31T07:00:00Z",
        "listing_ends": "2026-09-14T07:00:00Z",
        "seller": "clean_and_jerk",
        "size": "9",
        "is_active": 1,
    },
]

SAMPLE_WATCHES = [
    {
        "label": "My Size 10 Alert",
        "size_exact": "10",
        "min_size": None,
        "max_size": None,
        "max_price": 200.00,
        "min_price": None,
    },
    {
        "label": "Any Size Under $150",
        "size_exact": "",
        "min_size": None,
        "max_size": None,
        "max_price": 150.00,
        "min_price": None,
    },
]


def seed():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    existing = conn.execute("SELECT COUNT(*) as c FROM listings").fetchone()["c"]
    if existing > 0:
        print(f"DB already has {existing} listings — skipping seed")
        return

    for row in SAMPLE_LISTINGS:
        conn.execute(
            """INSERT INTO listings (item_id, title, price, currency, condition,
               item_url, image_url, shipping, accepts_offer, category,
               listed_at, listing_ends, seller, size, last_seen, is_active)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),?)""",
            tuple(row[k] for k in [
                "item_id", "title", "price", "currency", "condition",
                "item_url", "image_url", "shipping", "accepts_offer", "category",
                "listed_at", "listing_ends", "seller", "size", "is_active",
            ]),
        )

    for row in SAMPLE_WATCHES:
        conn.execute(
            "INSERT INTO watches (label, size_exact, min_size, max_size, max_price, min_price) VALUES (?,?,?,?,?,?)",
            (row["label"], row["size_exact"], row["min_size"], row["max_size"], row["max_price"], row["min_price"]),
        )

    conn.commit()
    count = conn.execute("SELECT COUNT(*) as c FROM listings").fetchone()["c"]
    wcount = conn.execute("SELECT COUNT(*) as c FROM watches").fetchone()["c"]
    conn.close()
    print(f"Seeded: {count} listings, {wcount} watches")


if __name__ == "__main__":
    seed()