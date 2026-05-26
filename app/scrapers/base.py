# app/scrapers/base.py

import json
import time
import random
import logging
from pathlib import Path
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base for all scrapers."""

    source: str           
    base_url: str         
    country: str          
    currency: str         
    
    
    delay_seconds: tuple = (2, 5)

    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]

    def __init__(self, output_dir: str = "data/raw"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.batch_id = f"{self.source}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        
        if self._client is None:
            self._client = httpx.Client(
                headers=self._get_headers(),
                timeout=30,
                follow_redirects=True,
            )
        return self._client

    def _get_headers(self) -> dict:
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def _delay(self):
       
        time.sleep(random.uniform(*self.delay_seconds))

    def _fetch(self, url: str) -> httpx.Response:
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._delay()
                logger.info(f"[{self.source}] GET {url} (attempt {attempt + 1})")
                response = self.client.get(url)
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

    def _get(self, url: str) -> Optional[httpx.Response]:
       
        try:
            return self._fetch(url)
        except Exception as e:
            logger.error(f"GET failed: {e}")
            return None

    def _parse_html(self, response: httpx.Response) -> BeautifulSoup:
        
        return BeautifulSoup(response.text, "html.parser")

    def _save_raw(self, data: list[dict]):
        
        filename = f"{self.batch_id}.json"
        filepath = self.output_dir / filename
        
        payload = {
            "batch_id": self.batch_id,
            "source": self.source,
            "country": self.country,
            "currency": self.currency,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "count": len(data),
            "listings": data,
        }
        
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        logger.info(f"Saved {len(data)} listings to {filepath}")
        return filepath

    @abstractmethod
    def scrape_listings(self, pages: int = 5) -> list[dict]:
        
        ...

    def run(self, pages: int = 5) -> list[dict]:
        
        logger.info(f"Starting {self.source} scraper ({pages} pages)...")
        listings = self.scrape_listings(pages=pages)
        self._save_raw(listings)
        logger.info(f"Finished {self.source}: {len(listings)} listings scraped.")
        return listings

    def close(self):
        
        if self._client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()