"""eBay Browse API client — OAuth2 + search.

Usage notes for eBay API compliance:
  * Browse API is limited to ~5,000 calls/day app-wide, so callers should
    poll on a sane interval and cache results rather than hitting the API
    on every page load.
  * Displayed listing data must be < 6h old; retention/expiry is handled
    by the caller (see ``database.enforce_retention``).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

# eBay Browse API accepts at most 200 items per search call.
MAX_LIMIT = 200
# Bound the 429 back-off so a rate-limited call can't hang a worker for long.
MAX_RETRY_WAIT = 10


class EbayClient:
    """Thin wrapper around eBay Browse API."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires: float = 0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = settings.ebay_user_agent

    def _get_token(self) -> str:
        """Obtain (or refresh) an OAuth2 application token."""
        if time.time() < self._token_expires and self._token:
            return self._token

        resp = self._session.post(
            TOKEN_URL,
            auth=(settings.ebay_client_id, settings.ebay_client_secret),
            data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires = time.time() + body.get("expires_in", 7200) - 60  # 1m buffer
        logger.info("Obtained fresh eBay OAuth2 token")
        return self._token  # type: ignore[return-value]

    def search(
        self,
        query: str,
        limit: int = 50,
        category_ids: str | None = None,
        sort: str = "newlyListed",
        filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search eBay Browse API for active listings.

        Returns a list of item summaries (dicts).  See the official eBay
        docs for the full response schema.
        """
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": settings.ebay_marketplace,
            "Accept": "application/json",
        }
        params: dict[str, Any] = {
            "q": query,
            "limit": max(1, min(limit, MAX_LIMIT)),
            "sort": sort,
        }
        if category_ids:
            params["category_ids"] = category_ids
        if filter:
            params["filter"] = filter

        resp = self._session.get(SEARCH_URL, headers=headers, params=params, timeout=20)
        if resp.status_code == 429:
            # Respect the server's back-off hint rather than guessing.
            wait = min(int(resp.headers.get("Retry-After", "2") or "2"), MAX_RETRY_WAIT)
            logger.warning("eBay rate-limited (429); backing off %ss and retrying once", wait)
            time.sleep(wait)
            resp = self._session.get(SEARCH_URL, headers=headers, params=params, timeout=20)

        resp.raise_for_status()
        body = resp.json()
        return body.get("itemSummaries", []) or []

    def search_romaleos2(
        self, limit: int = 50, sort: str = "newlyListed"
    ) -> list[dict[str, Any]]:
        """Convenience: search for Romaleos 2 with common aliases."""
        base = settings.default_search_query
        return self.search(query=base, limit=limit, sort=sort)


def parse_listing(item: dict[str, Any]) -> dict[str, Any]:
    """Normalise an eBay item summary into our row format."""
    price_info = item.get("price") or {}
    shipping_opts = item.get("shippingOptions") or []
    shipping_info = shipping_opts[0] if shipping_opts else {}
    shipping_cost = (shipping_info.get("shippingCost") or {}).get("value")

    title: str = item.get("title", "")
    buying_options = item.get("buyingOptions") or []

    return {
        "item_id": item.get("itemId", ""),
        "title": title,
        "price": float(price_info.get("value") or 0),
        "currency": price_info.get("currency", "USD"),
        "condition": item.get("condition"),
        "item_url": item.get("itemWebUrl", ""),
        "image_url": (item.get("image") or {}).get("imageUrl", ""),
        "shipping": float(shipping_cost) if shipping_cost is not None else 0.0,
        # Browse API reports best-offer availability via buyingOptions.
        "accepts_offer": 1 if "BEST_OFFER" in buying_options else 0,
        "category": (item.get("categories") or [{}])[0].get("categoryName", ""),
        "listed_at": item.get("itemCreationDate", ""),
        "listing_ends": item.get("itemEndDate", ""),
        "seller": (item.get("seller") or {}).get("username", ""),
        "size": _extract_size(title),
    }


# US shoe sizes we'll accept from a title (whole or half sizes).
_SIZE_RE = r"(?:[3-9]|1[0-8])(?:\.5)?"
_SIZE_PATTERNS = (
    re.compile(rf"(?:US|USM|USW|M|W|Men'?s?|Women'?s?|Mens|Womens|Unisex)\s*[:\-]?\s*({_SIZE_RE})\b", re.I),
    re.compile(rf"\b(?:size|sz|sze)\s*[:\-]?\s*({_SIZE_RE})\b", re.I),
    re.compile(rf"\b({_SIZE_RE})\s*(?:US\b|M\b|Mens\b|Men'?s\b)", re.I),
)


def _extract_size(title: str) -> str | None:
    """Best-effort US shoe size from a listing title.

    Only matches sizes preceded/followed by an explicit size marker
    (``US``/``Size``/``Men's``…) within the US 3–18 range, to avoid
    picking up model numbers ("Romaleos 2") and style codes ("476927-600").
    """
    if not title:
        return None
    for pat in _SIZE_PATTERNS:
        m = pat.search(title)
        if m:
            return m.group(1).lstrip("0") or m.group(1)
    return None


# Singleton
_client: EbayClient | None = None


def get_client() -> EbayClient:
    global _client
    if _client is None:
        _client = EbayClient()
    return _client
