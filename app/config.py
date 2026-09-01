"""Configuration loaded from environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    # eBay API
    # Support both the documented names and eBay's dashboard terminology.
    ebay_client_id: str = os.getenv("EBAY_CLIENT_ID") or os.getenv("APP_ID", "")
    ebay_client_secret: str = os.getenv("EBAY_CLIENT_SECRET") or os.getenv("CERT_ID", "")
    ebay_marketplace: str = os.getenv("EBAY_MARKETPLACE", "EBAY_US")
    ebay_currency: str = os.getenv("EBAY_CURRENCY", "USD")
    ebay_site_id: str = os.getenv("EBAY_SITE_ID", "0")  # 0 = US

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

    # Default search query
    default_search_query: str = os.getenv(
        "SEARCH_QUERY", "Nike Romaleos 2"
    )


settings = Settings()