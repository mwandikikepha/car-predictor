import json
import time
import random
import logging
from pathlib import Path
from datetime import datetime, timezone
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    source: str
    base_url: str
    country: str
    currency: str
    delay_seconds: tuple = (2, 5)

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4)...",
        "Mozilla/5.0 (X11; Linux x86_64)...",
    ]

    def __init__(self, output_dir: str = "data/raw"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.batch_id = f"{self.source}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.client = httpx.Client(
            headers=self._get_headers(),
            timeout=30,
            follow_redirects=True,
        )

    def _get_headers(self) -> dict:
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        }

    def _delay(self):
        time.sleep(random.uniform(*self.delay_seconds))

    def _fetch(self, url: str, **kwargs) -> httpx.Response:
        """GET with retry and polite delay."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._delay()
                logger.info(f"[{self.source}] GET {url} (attempt {attempt + 1})")
                response = self.client.get(url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = 10 * (attempt + 1)
                    logger.warning(f"Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise
            except Exception as e:
                logger.error(f"Request failed: {e}")
                if attempt == max_retries - 1:
                    raise
        raise RuntimeError("Max retries exceeded")

    def _save_raw(self, listings: list[dict]):
        filename = f"{self.batch_id}.json"
        filepath = self.output_dir / filename
        
        data = {
            "batch_id": self.batch_id,
            "source": self.source,
            "country": self.country,
            "currency": self.currency,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "count": len(listings),
            "listings": listings,
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Saved {len(listings)} listings to {filepath}")
        return filepath

    @abstractmethod
    def scrape_listings(self, pages: int = 5) -> list[dict]:
        ...

    def run(self, pages: int = 5) -> list[dict]:
        logger.info(f"Starting {self.source} ({pages} pages)...")
        listings = self.scrape_listings(pages=pages)
        self._save_raw(listings)
        logger.info(f"Done: {len(listings)} listings")
        return listings

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()