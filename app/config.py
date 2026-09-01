"""Configuration loaded from environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load a local .env if present.  On Replit the values arrive as real
# environment variables (Secrets) and this is a harmless no-op.
load_dotenv()


@dataclass
class Settings:
    # eBay API
    # Support both the documented names and eBay's dashboard terminology.
    ebay_client_id: str = os.getenv("EBAY_CLIENT_ID") or os.getenv("APP_ID", "")
    ebay_client_secret: str = os.getenv("EBAY_CLIENT_SECRET") or os.getenv("CERT_ID", "")
    ebay_marketplace: str = os.getenv("EBAY_MARKETPLACE", "EBAY_US")
    ebay_currency: str = os.getenv("EBAY_CURRENCY", "USD")
    ebay_site_id: str = os.getenv("EBAY_SITE_ID", "0")  # 0 = US
    ebay_user_agent: str = os.getenv(
        "EBAY_USER_AGENT", "romaleos-2-tracker/1.0 (+https://github.com/BUTTERGANG/romaleos-2-tracker)"
    )

    # App
    secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")
    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{Path(__file__).parent.parent / 'romaleos.db'}"
    )
    port: int = int(os.getenv("PORT", "8003"))
    host: str = os.getenv("HOST", "0.0.0.0")

    # Discord
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")

    # Scheduler
    poll_interval_minutes: int = int(os.getenv("POLL_INTERVAL_MINUTES", "30"))

    # ── eBay API compliance ────────────────────────────────────────────
    # The eBay API License Agreement requires that displayed listing data
    # be no more than 6 hours older than eBay's site (or that the age is
    # disclosed), and that data for items no longer available be deleted.
    # https://developer.ebay.com/develop/apis/api-license-agreement
    listing_stale_hours: float = float(os.getenv("LISTING_STALE_HOURS", "6"))
    listing_purge_hours: float = float(os.getenv("LISTING_PURGE_HOURS", "24"))
    # Minimum seconds between page-load-triggered live searches for the
    # same query+sort — protects the 5,000 calls/day Browse API budget.
    live_search_cache_seconds: float = float(os.getenv("LIVE_SEARCH_CACHE_SECONDS", "120"))

    # Default search query
    default_search_query: str = os.getenv("SEARCH_QUERY", "Nike Romaleos 2")

    @property
    def ebay_configured(self) -> bool:
        return bool(self.ebay_client_id and self.ebay_client_secret)


settings = Settings()
