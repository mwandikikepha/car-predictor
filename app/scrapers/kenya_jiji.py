# app/scrapers/kenya_jiji.py

import re
import logging
from playwright.sync_api import sync_playwright

from base import BaseScraper

logger = logging.getLogger(__name__)


class JijiKenyaScraper(BaseScraper):
    source = "jiji_kenya"
    base_url = "https://jiji.co.ke"
    country = "kenya"
    currency = "KES"

    def scrape_listings(self, pages: int = 5) -> list[dict]:
        listings = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            for pg in range(1, pages + 1):
                url = f"{self.base_url}/cars?page={pg}"
                logger.info(f"Scraping page {pg}: {url}")

                try:
                    page.goto(url, wait_until="load", timeout=30000)
                    page.wait_for_timeout(3000)

                    cards = page.query_selector_all(".js-advert-list-item")
                    if not cards:
                        logger.info(f"No cards on page {pg}, stopping")
                        break

                    for card in cards:
                        try:
                            listing = self._parse_card(card)
                            if listing:
                                listings.append(listing)
                        except Exception as e:
                            logger.warning(f"Skipped card: {e}")
                            continue

                    logger.info(f"Page {pg}: {len(cards)} cards, {len(listings)} total")

                except Exception as e:
                    logger.error(f"Failed page {pg}: {e}")
                    break

            browser.close()

        return listings

    def _parse_card(self, card) -> dict | None:
        card_text = card.inner_text()

        # Price
        price = self._extract_price(card_text)
        if not price:
            return None

        # Detail link
        link = card.query_selector('a[href*="/cars/"][href$=".html"]')
        if not link:
            return None

        href = link.get_attribute("href")
        url = href if href.startswith("http") else f"{self.base_url}{href}"

        # Parse URL for details: /mombasa-cbd/cars/honda-vezel-1-5-2wd-2020-blue-...html
        location, make, model, year, color, body_type = self._parse_url(href)

        # Description
        desc_el = card.query_selector("[class*=description], [class*=desc], [class*=title]")
        description = desc_el.inner_text().strip() if desc_el else ""

        # Transmission
        transmission = self._extract_transmission(card_text)

        # Foreign or Local used
        source_type = self._extract_source_type(card_text)

        # Mileage from description
        mileage = self._extract_mileage(description)

        # Engine size
        engine_size = self._extract_engine(description)

        # Image
        img = card.query_selector("img")
        image_url = img.get_attribute("src") or img.get_attribute("data-src") if img else None

        return {
            "source": self.source,
            "country": self.country,
            "currency": self.currency,
            "batch_id": self.batch_id,
            "make": make,
            "model": model,
            "year": year,
            "price": price,
            "mileage": mileage,
            "mileage_unit": "km",
            "engine_size": engine_size,
            "fuel_type": self._extract_fuel(description),
            "transmission": transmission,
            "body_type": body_type,
            "color": color,
            "drive_type": self._extract_drive(description),
            "url": url,
            "image_url": image_url,
            "location": location,
            "seller_type": None,
            "is_imported": True if source_type == "Foreign Used" else (False if source_type == "Local Used" else None),
            "description": description[:500] if description else None,
        }

    def _extract_price(self, text: str) -> float | None:
        """Extract price like 'KSh 4,900,000'."""
        match = re.search(r"KSh\s*([\d,]+)", text)
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    def _parse_url(self, href: str) -> tuple:
        """
        Parse: /mombasa-cbd/cars/honda-vezel-1-5-2wd-2020-blue-...html
        Returns: (location, make, model, year, color, body_type)
        """
        location = None
        make = None
        model = None
        year = None
        color = None
        body_type = None

        # Extract location (first segment)
        parts = href.strip("/").split("/")
        if len(parts) > 0 and parts[0] != "cars":
            location = parts[0].replace("-", " ").title()

        # Extract car details from last segment
        car_part = parts[-1].replace(".html", "") if parts else ""
        segments = car_part.split("-")

        # Common Kenyan car makes
        makes = ["toyota", "nissan", "honda", "mazda", "subaru", "mercedes", "bmw", "audi",
                 "volkswagen", "suzuki", "mitsubishi", "isuzu", "land", "range", "lexus", "jeep",
                 "ford", "hyundai", "kia", "peugeot", "volvo", "daihatsu"]

        # Common body types
        body_types = ["sedan", "hatchback", "suv", "pickup", "van", "wagon", "coupe",
                      "minivan", "convertible", "truck", "bus"]

        # Common colors
        colors = ["white", "black", "silver", "grey", "gray", "blue", "red", "green",
                  "yellow", "beige", "brown", "gold", "maroon", "pearl", "orange", "purple"]

        # Find make
        for i, seg in enumerate(segments):
            if seg.lower() in makes:
                make = seg
                # Model is next segments until we hit a year or other identifiable marker
                model_parts = []
                for j in range(i + 1, len(segments)):
                    s = segments[j]
                    if s.isdigit() and len(s) == 4:
                        year = int(s)
                        break
                    elif s.lower() in body_types:
                        body_type = s.capitalize()
                        break
                    elif s.lower() in colors:
                        break
                    else:
                        model_parts.append(s)
                if make.lower() == "land" and model_parts and model_parts[0].lower() in ["cruiser", "rover"]:
                    make = f"Land {model_parts.pop(0)}"
                model = " ".join(model_parts).title() if model_parts else None
                break

        # Find year
        if not year:
            for seg in segments:
                if seg.isdigit() and len(seg) == 4 and 1980 <= int(seg) <= 2026:
                    year = int(seg)
                    break

        # Find color
        for seg in reversed(segments):
            if seg.lower() in colors:
                color = seg.capitalize()
                break

        # Find body type
        if not body_type:
            for seg in segments:
                if seg.lower() in body_types:
                    body_type = seg.capitalize()
                    break

        return location, make, model, year, color, body_type

    def _extract_transmission(self, text: str) -> str | None:
        if re.search(r"\bAutomatic\b", text, re.IGNORECASE):
            return "Automatic"
        if re.search(r"\bManual\b", text, re.IGNORECASE):
            return "Manual"
        return None

    def _extract_source_type(self, text: str) -> str | None:
        """Foreign Used or Local Used."""
        if re.search(r"Foreign\s*Used", text, re.IGNORECASE):
            return "Foreign Used"
        if re.search(r"Local\s*Used", text, re.IGNORECASE):
            return "Local Used"
        return None

    def _extract_mileage(self, text: str) -> float | None:
        """Extract mileage from description like '120,000 km' or '120000km'."""
        match = re.search(r"([\d,]+)\s*km", text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    def _extract_engine(self, text: str) -> str | None:
        """Extract engine size like '2800cc' or '2.8 cc'."""
        match = re.search(r"(\d[\d,]*)\s*cc", text, re.IGNORECASE)
        if match:
            return match.group(1).replace(",", "")
        return None

    def _extract_fuel(self, text: str) -> str | None:
        fuels = ["Petrol", "Diesel", "Hybrid", "Electric"]
        for fuel in fuels:
            if re.search(rf"\b{fuel}\b", text, re.IGNORECASE):
                return fuel
        return None

    def _extract_drive(self, text: str) -> str | None:
        if re.search(r"\b4WD\b", text, re.IGNORECASE):
            return "4WD"
        if re.search(r"\bAWD\b", text, re.IGNORECASE):
            return "AWD"
        if re.search(r"\b2WD\b", text, re.IGNORECASE):
            return "2WD"
        return None