# app/scrapers/japan_beforward.py

import re
import logging
from typing import Optional
from base import BaseScraper

logger = logging.getLogger(__name__)

_MILEAGE_RE = re.compile(r'Mileage\s+([\d,]+)\s*km', re.IGNORECASE)
_YEAR_RE = re.compile(r'Year\s+([\d/]+)', re.IGNORECASE)
_ENGINE_RE = re.compile(r'Engine\s+([\d,]+)\s*cc', re.IGNORECASE)
_TRANS_RE = re.compile(r'Trans\.\s+([A-Z]+)', re.IGNORECASE)
_FUEL_RE = re.compile(r'Fuel\s+(Petrol|Diesel|Hybrid|Electric|LPG|CNG|Gasoline)', re.IGNORECASE)
_COLOR_RE = re.compile(r'Color\s+(\w+)', re.IGNORECASE)
_DRIVE_RE = re.compile(r'Drive\s+(2WD|4WD|AWD)', re.IGNORECASE)
_BODY_RE = re.compile(r'Body\s+(\w+)', re.IGNORECASE)
_REFNO_RE = re.compile(r'Ref\s*No\.?\s+([A-Z0-9]+)', re.IGNORECASE)

_CAR_URL_RE = re.compile(r'^/([a-z][a-z0-9\-]*)/([a-z0-9][a-z0-9\-]*)/([a-z0-9]+)/id/(\d+)/$')

MAKE_SLUG_MAP = {
    "toyota": "Toyota", "honda": "Honda", "nissan": "Nissan",
    "mazda": "Mazda", "subaru": "Subaru", "mitsubishi": "Mitsubishi",
    "suzuki": "Suzuki", "daihatsu": "Daihatsu", "isuzu": "Isuzu",
    "lexus": "Lexus", "infiniti": "Infiniti", "jeep": "Jeep",
    "mercedes-benz": "Mercedes-Benz", "bmw": "BMW", "volkswagen": "Volkswagen",
    "land-rover": "Land Rover", "mini": "MINI", "volvo": "Volvo",
}


class BeforwardScraper(BaseScraper):
    source = "beforward_japan"
    base_url = "https://www.beforward.jp"
    country = "japan"
    currency = "USD"

    def scrape_listings(self, pages: int = 5) -> list[dict]:
        listings = []
        seen_urls = set()

        for page in range(1, pages + 1):
            url = f"{self.base_url}/stocklist?page={page}&ipp=30"
            logger.info(f"Page {page}: {url}")

            response = self._get(url)
            if response is None:
                break

            soup = self._parse_html(response)
            cards = soup.find_all(["div", "tr"], class_="stocklist-row")

            if not cards:
                logger.info(f"No cards on page {page}, stopping")
                break

            for card in cards:
                try:
                    listing = self._parse_card(card)
                    if listing:
                        if listing.get("url") in seen_urls:
                            continue
                        seen_urls.add(listing["url"])
                        listings.append(listing)
                except Exception as e:
                    logger.warning(f"Skipped card: {e}")
                    continue

            logger.info(f"Page {page}: {len(cards)} cards, {len(listings)} total")
            if len(cards) < 3:
                break

        # Filter 2018+ in Python
        from datetime import datetime
        current_year = datetime.now().year
        listings = [l for l in listings if 2018 <= l.get("year", 0) <= current_year]
        logger.info(f"After year filter: {len(listings)} listings")
        return listings

    def _parse_card(self, card) -> Optional[dict]:
        try:
            if card.find(class_="price-col-sold"):
                return None

            link = card.find("a", class_="vehicle-url-link") or card.find("a", href=_CAR_URL_RE)
            if not link:
                return None

            href = link.get("href", "")
            m = _CAR_URL_RE.match(href)
            if not m:
                return None

            make_slug, model_slug, stock_code, listing_id = m.groups()

            data = {
                "source": self.source,
                "country": self.country,
                "currency": self.currency,
                "batch_id": self.batch_id,
                "make": MAKE_SLUG_MAP.get(make_slug, make_slug.replace("-", " ").title()),
                "model": model_slug.replace("-", " ").title(),
                "stock_id": stock_code.upper(),
            }

            text = card.get_text(" ", strip=True)

            ref_m = _REFNO_RE.search(text)
            if ref_m:
                data["stock_id"] = ref_m.group(1)

            price_span = card.find("span", class_="price")
            if price_span:
                raw = price_span.get_text(strip=True).replace("$", "").replace(",", "")
                try:
                    data["price"] = float(raw)
                except ValueError:
                    pass

            mileage_m = _MILEAGE_RE.search(text)
            if mileage_m:
                data["mileage"] = int(mileage_m.group(1).replace(",", ""))
                data["mileage_unit"] = "km"

            year_m = _YEAR_RE.search(text)
            if year_m:
                yr_str = year_m.group(1).split("/")[0]
                if yr_str.isdigit():
                    data["year"] = int(yr_str)

            engine_m = _ENGINE_RE.search(text)
            if engine_m:
                data["engine_size"] = engine_m.group(1).replace(",", "")

            trans_m = _TRANS_RE.search(text)
            if trans_m:
                data["transmission"] = trans_m.group(1)

            fuel_m = _FUEL_RE.search(text)
            if fuel_m:
                data["fuel_type"] = fuel_m.group(1).strip()

            color_m = _COLOR_RE.search(text)
            if color_m:
                data["body_color"] = color_m.group(1).strip().title()

            drive_m = _DRIVE_RE.search(text)
            if drive_m:
                data["drive_type"] = drive_m.group(1)

            body_m = _BODY_RE.search(text)
            if body_m:
                data["body_type"] = body_m.group(1).strip().title()

            data["url"] = self.base_url + href

            if not data.get("price") or not data.get("make"):
                return None

            return data

        except Exception as e:
            logger.debug(f"Card parse error: {e}")
            return None