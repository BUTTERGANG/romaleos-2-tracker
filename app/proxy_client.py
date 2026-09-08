"""
Proxy client — drop-in alternative to app/ebay_client.py.

Routes all eBay searches through the shared eBay API Proxy.
Same interface as EbayClient but no OAuth or keys needed.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_PROXY_URL = os.environ.get("EBAY_PROXY_URL", "http://localhost:8080")
DEFAULT_PROXY_TOKEN = os.environ.get("EBAY_PROXY_TOKEN", "")


class ProxyClient:
    """eBay Browse API via the shared proxy.

    Mirrors the interface of app.ebay_client.EbayClient but routes
    through the eBay API Proxy instead of hitting eBay directly.
    """

    def __init__(self, proxy_url: str | None = None, proxy_token: str | None = None) -> None:
        self.proxy_url = (proxy_url or DEFAULT_PROXY_URL).rstrip("/")
        self.proxy_token = proxy_token or DEFAULT_PROXY_TOKEN
        self._client = httpx.Client(base_url=self.proxy_url, timeout=20)

    def _get(self, endpoint: str, params: dict) -> dict | None:
        """Make an authenticated GET to the proxy."""
        try:
            resp = self._client.get(
                endpoint,
                params=params,
                headers={"Authorization": f"Bearer {self.proxy_token}"},
            )
            if resp.status_code == 401:
                logger.error("Proxy auth failed — check EBAY_PROXY_TOKEN")
                return None
            if resp.status_code == 429:
                logger.warning("Proxy rate-limited, backing off 2s")
                time.sleep(2)
                return self._get(endpoint, params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Proxy HTTP {e.response.status_code}: {e.response.text[:200]}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Proxy request failed ({self.proxy_url}): {e}")
            return None

    def search(
        self,
        query: str,
        limit: int = 50,
        category_ids: str | None = None,
        sort: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search eBay via proxy for active listings.

        Returns item summaries matching the same shape as ebay_client.EbayClient.search().
        """
        params: dict[str, Any] = {"q": query, "limit": str(min(limit, 200))}
        if category_ids:
            params["category"] = category_ids

        data = self._get("/comps", params)
        if not data:
            return []
        return data.get("items", [])

    def search_romaleos2(
        self, limit: int = 50, sort: str | None = None
    ) -> list[dict[str, Any]]:
        """Convenience: search for Romaleos 2 with common aliases."""
        base = settings.default_search_query
        return self.search(query=base, limit=limit, sort=sort)

    def close(self):
        self._client.close()


# ---------------------------------------------------------------------------
# Shared parser — identical to app/ebay_client.parse_listing
# ---------------------------------------------------------------------------

def parse_listing(item: dict[str, Any]) -> dict[str, Any]:
    """Normalise an eBay item summary into our row format.

    Mirrors app/ebay_client.parse_listing exactly.
    """
    price_info = item.get("price", {})
    shipping_info = item.get("shippingOptions", [{}])[0] if item.get("shippingOptions") else {}

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

    Mirrors app/ebay_client._extract_size exactly.
    """
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


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_client: ProxyClient | None = None


def get_client() -> ProxyClient:
    global _client
    if _client is None:
        _client = ProxyClient()
    return _client