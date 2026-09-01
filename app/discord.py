"""Discord delivery.

This is an *incoming webhook* integration, not a gateway bot: the app only
POSTs messages to a channel webhook. It handles Discord's rate limits (429 +
retry_after), transient 5xx/network errors with bounded retries, batches up to
10 embeds per request, and can fan out to a per-watch webhook URL.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers["User-Agent"] = settings.ebay_user_agent

EMBEDS_PER_MESSAGE = 10   # Discord hard limit
MAX_ATTEMPTS = 4
MAX_BACKOFF_SECONDS = 30
_TITLE_MAX = 256
_VALUE_MAX = 1024
_FOOTER_MAX = 2048
_EMBED_COLOR = 0x3FB950   # green


def _truncate(text: str | None, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _iso_or_none(ts: str | None) -> str | None:
    """Return ts only if Discord will accept it as an ISO-8601 timestamp."""
    if not ts:
        return None
    try:
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts


def build_embed(listing: dict[str, Any], watch_label: str = "") -> dict[str, Any]:
    price = listing.get("price") or 0
    currency = listing.get("currency") or "USD"
    shipping = listing.get("shipping") or 0
    ship_txt = f"+{currency} {shipping:.2f}" if shipping else "Free"
    offers = "✅ Accepting offers" if listing.get("accepts_offer") else "❌ Fixed price"

    embed: dict[str, Any] = {
        "title": _truncate(listing.get("title") or "Romaleos 2 listing", _TITLE_MAX),
        "url": listing.get("item_url") or None,
        "color": _EMBED_COLOR,
        "fields": [
            {"name": "Price", "value": _truncate(f"{currency} {price:.2f}", _VALUE_MAX), "inline": True},
            {"name": "Shipping", "value": _truncate(ship_txt, _VALUE_MAX), "inline": True},
            {"name": "Size", "value": _truncate(f"US {listing.get('size')}" if listing.get("size") else "—", _VALUE_MAX), "inline": True},
            {"name": "Condition", "value": _truncate(listing.get("condition") or "N/A", _VALUE_MAX), "inline": True},
            {"name": "Offers", "value": offers, "inline": True},
            {"name": "Seller", "value": _truncate(listing.get("seller") or "Unknown", _VALUE_MAX), "inline": True},
        ],
    }
    if listing.get("image_url"):
        embed["thumbnail"] = {"url": listing["image_url"]}
    if watch_label:
        embed["footer"] = {"text": _truncate(f"Watch: {watch_label}", _FOOTER_MAX)}
    ts = _iso_or_none(listing.get("listed_at"))
    if ts:
        embed["timestamp"] = ts
    return embed


def _post(url: str, payload: dict[str, Any]) -> bool:
    """POST one webhook message. Retries 429/5xx/network up to MAX_ATTEMPTS."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = _session.post(url, json=payload, timeout=10)
        except requests.RequestException as e:
            logger.warning("Discord POST error (attempt %d/%d): %s", attempt, MAX_ATTEMPTS, e)
            if attempt == MAX_ATTEMPTS:
                return False
            time.sleep(min(2 ** attempt, MAX_BACKOFF_SECONDS))
            continue

        if resp.status_code in (200, 204):
            return True

        if resp.status_code == 429:
            retry_after = _retry_after(resp)
            logger.warning("Discord rate-limited; sleeping %.2fs then retrying", retry_after)
            time.sleep(retry_after)
            continue

        if 500 <= resp.status_code < 600:
            logger.warning("Discord %d (attempt %d/%d)", resp.status_code, attempt, MAX_ATTEMPTS)
            if attempt == MAX_ATTEMPTS:
                return False
            time.sleep(min(2 ** attempt, MAX_BACKOFF_SECONDS))
            continue

        # Other 4xx: bad URL, deleted webhook, malformed payload — no point retrying.
        logger.error("Discord webhook rejected: %s %s", resp.status_code, resp.text[:300])
        return False

    return False


def _retry_after(resp: requests.Response) -> float:
    try:
        value = float(resp.json().get("retry_after"))
    except (ValueError, TypeError, AttributeError, requests.JSONDecodeError):
        try:
            value = float(resp.headers.get("Retry-After", "1"))
        except (ValueError, TypeError):
            value = 1.0
    return max(0.0, min(value, MAX_BACKOFF_SECONDS))


def send_matches(matches: list[dict[str, Any]], default_url: str | None = None) -> set[tuple[int, str]]:
    """Deliver watch matches, grouped per webhook and batched ≤10 embeds/message.

    Each match dict: ``{"watch_id", "listing_id", "listing", "watch_label",
    "webhook_url"}``. Returns the set of ``(watch_id, listing_id)`` delivered,
    so the caller records only what actually went out (the rest retry next poll).
    """
    default_url = settings.discord_webhook_url if default_url is None else default_url

    groups: dict[str, list[dict[str, Any]]] = {}
    for m in matches:
        url = m.get("webhook_url") or default_url
        if url:
            groups.setdefault(url, []).append(m)

    delivered: set[tuple[int, str]] = set()
    for url, group in groups.items():
        for i in range(0, len(group), EMBEDS_PER_MESSAGE):
            chunk = group[i : i + EMBEDS_PER_MESSAGE]
            payload = {"embeds": [build_embed(m["listing"], m.get("watch_label", "")) for m in chunk]}
            if _post(url, payload):
                delivered.update((m["watch_id"], m["listing_id"]) for m in chunk)
            else:
                logger.warning(
                    "Discord delivery failed for %d match(es); will retry next poll", len(chunk)
                )
    return delivered


def send_notification(listing: dict[str, Any], watch_label: str = "", webhook_url: str | None = None) -> bool:
    """Single-embed convenience wrapper (used for one-off sends)."""
    url = webhook_url or settings.discord_webhook_url
    if not url:
        logger.debug("No Discord webhook URL configured — skipping notification")
        return False
    return _post(url, {"embeds": [build_embed(listing, watch_label)]})


def send_test_notification(webhook_url: str) -> bool:
    """Post a plain message to verify a webhook works."""
    return _post(
        webhook_url,
        {"content": "🔔 **ROMALEOS 2 Tracker** — Discord alerts are live. "
                    "Matching listings will show up here."},
    )
