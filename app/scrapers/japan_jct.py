# app/scrapers/japan_jct.py

import re
import logging
from playwright.sync_api import sync_playwright

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class JCTScraper(BaseScraper):
    source = "jct"
    base_url = "https://www.japanesecartrade.com"
    country = "japan"
    currency = "USD"

    def scrape_listings(self, pages: int = 5) -> list[dict]:
        listings = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            for pg in range(1, pages + 1):
                url = f"{self.base_url}/stock_list.php?year_from=2018&page={pg}"
                logger.info(f"Scraping page {pg}: {url}")

                try:
                    page.goto(url, wait_until="load", timeout=30000)
                    page.wait_for_timeout(5000)

                    cards = page.query_selector_all(".stock_list_first")
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

                    # Polite delay between pages
                    if pg < pages:
                        page.wait_for_timeout(8000)

                except Exception as e:
                    logger.error(f"Failed page {pg}: {e}")
                    break

            browser.close()

        return listings

    def _parse_card(self, card) -> dict | None:
        # Title: "Toyota Corolla (2000)" inside h2.list_head a
        title_el = card.query_selector("h2.list_head a")
        if not title_el:
            return None
        title = title_el.inner_text().strip()

        year = self._extract_year(title)
        make = self._extract_make(title)
        model = self._extract_model(title, make)

        # Detail URL
        url = title_el.get_attribute("href")
        if url and not url.startswith("http"):
            url = self.base_url + url

        # Image
        img_el = card.query_selector(".list_image img")
        image_url = img_el.get_attribute("src") if img_el else None

        # Full card text for parsing
        card_text = card.inner_text()

        # FOB Price
        price = self._extract_price(card_text)

        if not price:
            return None

        # Mileage
        mileage = self._extract_mileage(card_text)

        # Engine CC
        engine = self._extract_engine_cc(card_text)

        # Fuel type
        fuel = self._extract_fuel(card_text)

        # Transmission
        transmission = self._extract_transmission(card_text)

        # Body type
        body_type = self._extract_body_type(card_text)

        # Location
        location = self._extract_location(card_text)

        # Stock/chassis ID
        chassis = self._extract_chassis(card_text)

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
            "engine_size": engine,
            "fuel_type": fuel,
            "transmission": transmission,
            "body_type": body_type,
            "drive_type": "RHD",  # JCT is mostly RHD
            "chassis": chassis,
            "url": url,
            "image_url": image_url,
            "location": location,
            "stock_id": card.get_attribute("class").split()[-1] if card.get_attribute("class") else None,
        }

    def _extract_year(self, title: str) -> int | None:
        """Extract year from 'Toyota Corolla (2000)' or 'Nissan Skyline DAA-HV37 (2014/03)'."""
        match = re.search(r"\((\d{4})(?:/\d{2})?\)", title)
        if match:
            return int(match.group(1))
        return None

    def _extract_make(self, title: str) -> str | None:
        """First word is usually the make."""
        parts = title.split()
        return parts[0] if parts else None

    def _extract_model(self, title: str, make: str | None) -> str | None:
        """Everything between make and the year."""
        match = re.search(r"\((\d{4})", title)
        if match and make:
            model_part = title[len(make):match.start()].strip()
            return model_part if model_part else None
        return None

    def _extract_price(self, text: str) -> float | None:
        """FOB price: 'FOB : 14,000 USD' or 'FOB : ASK'."""
        match = re.search(r"FOB\s*:\s*([\d,]+)\s*(?:USD)?", text)
        if match:
            return float(match.group(1).replace(",", ""))
        # Also try just a dollar amount
        match = re.search(r"([\d,]+)\s*USD", text)
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    def _extract_mileage(self, text: str) -> float | None:
        """Extract '133,700 KM' or '57,000 KM'."""
        match = re.search(r"([\d,]+)\s*KM", text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    def _extract_engine_cc(self, text: str) -> str | None:
        """Extract '660 CC' or '1,300 CC'."""
        match = re.search(r"([\d,]+)\s*CC", text, re.IGNORECASE)
        if match:
            return match.group(1).replace(",", "")
        return None

    def _extract_fuel(self, text: str) -> str | None:
        """Extract fuel type."""
        fuels = ["Petrol", "Diesel", "Hybrid", "Electric", "CNG", "LPG"]
        for fuel in fuels:
            if re.search(rf"\b{fuel}\b", text, re.IGNORECASE):
                return fuel.capitalize()
        return None

    def _extract_transmission(self, text: str) -> str | None:
        """Extract transmission type."""
        if re.search(r"\bAutomatic\b", text, re.IGNORECASE):
            return "Automatic"
        if re.search(r"\bManual\b", text, re.IGNORECASE):
            return "Manual"
        if re.search(r"\bCVT\b", text, re.IGNORECASE):
            return "CVT"
        return None

    def _extract_body_type(self, text: str) -> str | None:
        """Extract body type from card text."""
        body_types = [
            "Sedan", "Hatchback", "SUV", "Mini Truck", "Flatbody Truck",
            "Van", "Minivan", "Long Van", "Pickup", "Coupe", "Wagon",
            "Convertible", "Bus", "Truck", "Other",
        ]
        for bt in body_types:
            if re.search(rf"\b{bt}\b", text, re.IGNORECASE):
                return bt
        return None

    def _extract_location(self, text: str) -> str | None:
        """Extract location like 'Yokohama' or 'Sagamihara, Japan'."""
        # Often after "Select Country & Port" or near the end
        match = re.search(r"(?:Japan\s*[»>]\s*|Location\s*:\s*)(\w+)", text)
        if match:
            return match.group(1)
        return None

    def _extract_chassis(self, text: str) -> str | None:
        """Extract chassis number."""
        match = re.search(r"Chassis No\.?\s*:\s*(\S+)", text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None