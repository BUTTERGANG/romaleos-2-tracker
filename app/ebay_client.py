"""eBay Browse API client — OAuth2 + search."""

from __future__ import annotations

import time
import logging
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


class EbayClient:
    """Thin wrapper around eBay Browse API."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires: float = 0

    def _get_token(self) -> str:
        """Obtain (or refresh) an OAuth2 application token."""
        if time.time() < self._token_expires and self._token:
            return self._token

        resp = requests.post(
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
        params = {
            "q": query,
            "limit": min(limit, 200),
            "sort": sort,
        }
        if category_ids:
            params["category_ids"] = category_ids

        resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=20)
        if resp.status_code == 429:
            logger.warning("eBay rate-limited; backing off 2s and retrying")
            time.sleep(2)
            resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=20)

        resp.raise_for_status()
        body = resp.json()
        return body.get("itemSummaries", [])

    def search_romaleos2(
        self, limit: int = 50, sort: str = "newlyListed"
    ) -> list[dict[str, Any]]:
        """Convenience: search for Romaleos 2 with common aliases."""
        base = settings.default_search_query
        return self.search(query=base, limit=limit, sort=sort)


def parse_listing(item: dict[str, Any]) -> dict[str, Any]:
    """Normalise an eBay item summary into our row format."""
    price_info = item.get("price", {})
    shipping_info = item.get("shippingOptions", [{}])[0] if item.get("shippingOptions") else {}

    # Extract size from title
    title: str = item.get("title", "")
    size = _extract_size(title)

    return {
        "item_id": item.get("itemId", ""),
        "title": title,
        "price": float(price_info.get("value", 0)),
        "currency": price_info.get("currency", "USD"),
        "condition": item.get("condition"),
        "item_url": item.get("itemWebUrl", ""),
        "image_url": (item.get("image", {}) or {}).get("imageUrl", ""),
        "shipping": float(shipping_info.get("shippingCost", {}).get("value", 0))
            if shipping_info.get("shippingCost") else 0,
        "accepts_offer": 1 if item.get("itemCreationDate") and
            item.get("sellingState") != "ENDED" and
            item.get("isAcceptingOffer", False) else 0,
        "category": (item.get("categories") or [{}])[0].get("categoryName", "")
            if item.get("categories") else "",
        "listed_at": item.get("itemCreationDate", ""),
        "listing_ends": item.get("itemEndDate", ""),
        "seller": (item.get("seller", {}) or {}).get("username", ""),
        "size": size,
    }


def _extract_size(title: str) -> str | None:
    """Attempt to extract a shoe size from the listing title.

    Looks for patterns like "US 10", "Size 11", "10.5 UK", "EU 44".
    """
    import re

    # Common patterns: US 10, Size 11, 10.5, EU 44, UK 9
    patterns = [
        r"(?:US|M|W|Men|Women|Unisex)\s*(\d{1,2}(?:\.5)?)",  # "US 10", "Men 8"
        r"(\d{1,2}(?:\.5)?)\s*(?:US|UK|EU|CM)",  # "10 US", "44 EU"
        r"(?:Size|sz|sze)\s*(\d{1,2}(?:\.5)?)",  # "Size 11", "sz 10"
        r"\b(\d{1,2}\.\d)\b",  # standalone decimal like "10.5"
    ]
    for pat in patterns:
        m = re.search(pat, title, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


# Singleton
_client: EbayClient | None = None


def get_client() -> EbayClient:
    global _client
    if _client is None:
        _client = EbayClient()
    return _client