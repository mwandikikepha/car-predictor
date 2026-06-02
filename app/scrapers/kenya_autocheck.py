import re
import time
import random
import logging
from playwright.sync_api import sync_playwright

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class AutocheckKenyaScraper(BaseScraper):
    source = "autocheck_kenya"
    base_url = "https://autochek.africa"
    country = "kenya"
    currency = "KES"
    
    def scrape_listings(self, pages: int = 5) -> list[dict]:
        listings = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            url = f"{self.base_url}/ke/cars-for-sale"
            logger.info(f"Loading: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            for pg in range(1, pages + 1):
                logger.info(f"Scraping page {pg}")

                cards = page.query_selector_all(".car-card")
                if not cards:
                    logger.info("No cards, stopping")
                    break

                # Parse basics from current page
                basics = []
                for card in cards:
                    try:
                        basic = self._parse_card(card)
                        if basic and basic.get("make") and basic.get("model"):
                            basics.append(basic)
                    except Exception as e:
                        logger.warning(f"Basic parse error: {e}")
                        continue

                # Visit detail pages
                page_results = 0
                for basic in basics:
                    try:
                        detail_page = browser.new_page()
                        detail = self._scrape_detail_page(detail_page, basic["url"])
                        detail_page.close()

                        for key, value in detail.items():
                            if value is not None:
                                basic[key] = value

                        if basic.get("year") and 2010 <= basic["year"] <= 2026:
                            listings.append(basic)
                            page_results += 1

                        time.sleep(random.uniform(0.3, 1.0))
                    except Exception as e:
                        logger.warning(f"Detail failed: {e}")
                        if basic.get("year") and 2010 <= basic["year"] <= 2026:
                            listings.append(basic)
                            page_results += 1
                        continue

                logger.info(f"Page {pg}: {page_results} valid from {len(cards)} cards, {len(listings)} total")

                # Click next page number (not URL change)
                if pg < pages:
                    next_page_num = str(pg + 1)
                    next_btn = page.query_selector(f"button.MuiPaginationItem-root:has-text('{next_page_num}')")
                    if next_btn:
                        next_btn.click()
                        page.wait_for_timeout(3000)
                    else:
                        logger.info("No more pages")
                        break

            browser.close()

        return listings

    def _parse_card(self, card) -> dict | None:
        """Extract info from the search result card."""
        try:
            text = card.inner_text()

            price = self._extract_price(text)
            if not price:
                return None

            link = card.query_selector("a[href*='cars-for-sale']")
            if not link:
                return None

            href = link.get_attribute("href")
            url = href if href.startswith("http") else f"{self.base_url}{href}"

            make, model, year = self._parse_title_and_url(card, href)

            if not make or not model:
                return None

            source_type = self._extract_source_type(text)
            mileage = self._extract_mileage(text)
            location = self._extract_location(text)

            img = card.query_selector("img")
            image_url = img.get_attribute("src") if img else None

            # Extract transmission from card text
            transmission = None
            if "automatic" in text.lower():
                transmission = "Automatic"
            elif "manual" in text.lower():
                transmission = "Manual"

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
                "transmission": transmission,
                "url": url,
                "image_url": image_url,
                "location": location,
                "is_imported": True if source_type == "Foreign" else (False if source_type == "Local" else None),
            }

        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return None
        
    def _scrape_detail_page(self, page, url: str) -> dict:
        """Visit detail page and extract full vehicle specs."""
        detail = {
            "engine_size": None,
            "fuel_type": None,
            "transmission": None,
            "body_type": None,
            "color": None,
            "drive_type": None,
            "seller_type": None,
        }

        try:
            # Use 'load' and shorter timeout, continue on timeout
            try:
                page.goto(url, wait_until="load", timeout=15000)
            except:
                pass

            page.wait_for_timeout(1000)

            # Accept cookies if present
            try:
                accept_btn = page.query_selector("button:has-text('Accept'), button:has-text('I Accept'), button:has-text('accept')")
                if accept_btn:
                    accept_btn.click()
                    page.wait_for_timeout(500)
            except:
                pass

            text = page.inner_text("body")
            page_text = text.lower()

            # Transmission
            if "automatic" in page_text:
                detail["transmission"] = "Automatic"
            elif "manual" in page_text:
                detail["transmission"] = "Manual"

            # Engine: "2700 cc"
            engine_match = re.search(r'(\d[\d,]*)\s*cc', text, re.IGNORECASE)
            if engine_match:
                detail["engine_size"] = engine_match.group(1).replace(",", "")

            # Fuel type
            fuel_match = re.search(r'(?:fuel\s*type|fuel)\s*[:\n]\s*(.+)', text, re.IGNORECASE)
            if fuel_match:
                fuel = fuel_match.group(1).strip().split('\n')[0].title()
                if "hybrid" in fuel.lower() and "petrol" in fuel.lower():
                    detail["fuel_type"] = "Hybrid-Petrol"
                elif "hybrid" in fuel.lower():
                    detail["fuel_type"] = "Hybrid"
                elif "diesel" in fuel.lower():
                    detail["fuel_type"] = "Diesel"
                elif "petrol" in fuel.lower():
                    detail["fuel_type"] = "Petrol"
                elif "electric" in fuel.lower():
                    detail["fuel_type"] = "Electric"
            else:
                if "hybrid" in page_text:
                    detail["fuel_type"] = "Hybrid"
                elif "diesel" in page_text:
                    detail["fuel_type"] = "Diesel"
                elif "petrol" in page_text:
                    detail["fuel_type"] = "Petrol"

            # Body type with word boundaries
            body_types = ["sedan", "hatchback", "suv", "pickup", "van", "wagon",
                        "coupe", "minivan", "convertible", "truck", "bus"]
            for bt in body_types:
                if re.search(rf'\b{bt}\b', page_text):
                    detail["body_type"] = bt.capitalize()
                    break

            # Color
            color_match = re.search(r'exterior\s*color\s*[:\n]\s*(.+)', text, re.IGNORECASE)
            if color_match:
                detail["color"] = color_match.group(1).strip().split('\n')[0].title()

            # Drive type
            if re.search(r'\b4wd\b|\b4x4\b', page_text):
                detail["drive_type"] = "4WD"
            elif re.search(r'\bawd\b|all\s*wheel', page_text):
                detail["drive_type"] = "AWD"
            elif re.search(r'\b2wd\b|\bfwd\b|front\s*wheel', page_text):
                detail["drive_type"] = "2WD"

        except Exception as e:
            logger.warning(f"Detail scrape failed for {url}: {e}")

        return detail


    def _extract_price(self, text: str) -> float | None:
        match = re.search(r"KSh\s*([\d,]+)", text)
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    def _parse_title_and_url(self, card, href: str) -> tuple:
   
        make = None
        model = None
        year = None

        # Find H6 with class containing "MuiTypography-h6"
        h6_elements = card.query_selector_all("h6")
        for h6 in h6_elements:
            text = h6.inner_text().strip()
            # Pattern: "2017 Mitsubishi Gk wagon"
            match = re.match(r'(\d{4})\s+(.+)', text)
            if match:
                year = int(match.group(1))
                rest = match.group(2)
                parts = rest.split(" ", 1)
                make = parts[0] if parts else None
                model = parts[1] if len(parts) > 1 else None
                break

        # Fallback: URL
        if not make or not model:
            parts = href.strip("/").split("/")
            if len(parts) >= 4:
                make = parts[2].replace("-", " ").title()
                model = parts[3].replace("-", " ").title()

        return make, model, year

    def _extract_source_type(self, text: str) -> str | None:
        if re.search(r'\bForeign\b', text, re.IGNORECASE):
            return "Foreign"
        if re.search(r'\bLocal\b', text, re.IGNORECASE):
            return "Local"
        return None

    def _extract_mileage(self, text: str) -> float | None:
        match = re.search(r'(\d+(?:\.\d+)?)\s*K\s*kms', text, re.IGNORECASE)
        if match:
            return float(match.group(1)) * 1000
        match = re.search(r'([\d,]+)\s*kms', text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    def _extract_location(self, text: str) -> str | None:
        locations = ["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret", "Thika",
                     "Kiambu", "Machakos", "Nyeri", "Meru", "Kitale", "Malindi"]
        for loc in locations:
            match = re.search(rf'({loc}[,\s\w]*)', text, re.IGNORECASE)
            if match:
                return match.group(1).strip().rstrip("KSh").strip()
        return None