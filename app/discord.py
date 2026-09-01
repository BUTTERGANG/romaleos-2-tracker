"""Discord webhook notification module."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)


def send_notification(
    listing: dict[str, Any],
    watch_label: str = "",
    webhook_url: str | None = None,
) -> bool:
    """Send a Discord embed notification for a matched listing.

    Returns True on success, False otherwise.
    """
    url = webhook_url or settings.discord_webhook_url
    if not url:
        logger.debug("No Discord webhook URL configured — skipping notification")
        return False

    condition = listing.get("condition", "N/A")
    price = listing.get("price", 0)
    currency = listing.get("currency", "USD")
    title = listing.get("title", "Unknown")
    item_url = listing.get("item_url", "")
    image_url = listing.get("image_url", "")
    size = listing.get("size", "Unknown")
    offers = "✅ Accepting Offers" if listing.get("accepts_offer") else ""

    embed = {
        "embeds": [
            {
                "title": f"💰 Romaleos 2 Found — {currency} {price:.2f}",
                "url": item_url,
                "color": 0x00FF00,  # green
                "fields": [
                    {"name": "Title", "value": title[:256], "inline": False},
                    {"name": "Price", "value": f"{currency} {price:.2f}", "inline": True},
                    {"name": "Condition", "value": condition, "inline": True},
                    {"name": "Size", "value": str(size), "inline": True},
                    {"name": "Offers", "value": offers or "❌ Fixed Price", "inline": True},
                ],
                "thumbnail": {"url": image_url} if image_url else None,
                "footer": (
                    {"text": f"Watch: {watch_label}"}
                    if watch_label
                    else None
                ),
                "timestamp": listing.get("listed_at", ""),
            }
        ]
    }
    # Remove null fields
    embed["embeds"][0] = {k: v for k, v in embed["embeds"][0].items() if v is not None}

    resp = requests.post(url, json=embed, timeout=10)
    if resp.status_code not in (200, 204):
        logger.error("Discord webhook returned %s: %s", resp.status_code, resp.text[:200])
        return False
    logger.info("Discord notification sent for %s", listing.get("item_id"))
    return True


def send_test_notification(webhook_url: str) -> bool:
    """Send a test ping to verify webhook configuration."""
    payload = {
        "content": "🔔 **ROMALEOS 2 Tracker** — Discord notifications are live! Watches will appear here when matching shoes are found."
    }
    resp = requests.post(webhook_url, json=payload, timeout=10)
    if resp.status_code not in (200, 204):
        logger.error("Test webhook returned %s: %s", resp.status_code, resp.text[:200])
        return False
    return True