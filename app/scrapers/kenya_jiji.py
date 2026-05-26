# app/scrapers/kenya_jiji.py

import re
import time
import random
import logging
from playwright.sync_api import sync_playwright

from base import BaseScraper

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r'^20(?:[0-2]\d)$')


class JijiKenyaScraper(BaseScraper):
    source = "jiji_kenya"
    base_url = "https://jiji.co.ke"
    country = "kenya"
    currency = "KES"

    def scrape_listings(self, pages: int = 25) -> list[dict]:
        listings = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            list_page = context.new_page()
            detail_page = context.new_page()

            for pg in range(1, pages + 1):
                url = f"{self.base_url}/cars?page={pg}"
                logger.info(f"Scraping page {pg}: {url}")

                try:
                    list_page.goto(url, wait_until="networkidle", timeout=60000)
                    list_page.wait_for_timeout(2000)

                    cards = list_page.query_selector_all(".js-advert-list-item")
                    if not cards:
                        logger.info(f"No cards on page {pg}, stopping")
                        break

                    for card in cards:
                        try:
                            basic = self._parse_card_basic(card)
                            if not basic:
                                continue
                            
                            detail = self._scrape_detail_page(detail_page, basic["url"])
                            listing = {**basic, **detail}
                            
                            if not listing.get("make") or not listing.get("model"):
                                continue
                            if not listing.get("year") or not (1990 <= listing["year"] <= 2026):
                                continue
                            
                            listings.append(listing)
                            time.sleep(random.uniform(0.5, 1.0))
                            
                        except Exception as e:
                            logger.warning(f"Card error: {e}")
                            continue

                    logger.info(f"Page {pg}: {len(cards)} cards, {len(listings)} total")

                except Exception as e:
                    logger.error(f"Failed page {pg}: {e}")
                    break

            browser.close()

        return listings

    def _parse_card_basic(self, card) -> dict | None:
        try:
            card_text = card.inner_text()

            price = self._extract_price(card_text)
            if not price:
                return None

            link = card.query_selector('a[href*="/cars/"]')
            if not link:
                return None

            href = link.get_attribute("href") or ""
            href = href.split('?')[0]
            url = href if href.startswith("http") else f"{self.base_url}{href}"

            location, make, model, year, color, body_type = self._parse_url(href)

            desc_el = card.query_selector("[class*=description], [class*=desc], [class*=title]")
            description = desc_el.inner_text().strip() if desc_el else ""

            img = card.query_selector("img")
            image_url = None
            if img:
                image_url = img.get_attribute("data-src") or img.get_attribute("src")

            transmission = self._extract_transmission(card_text)
            source_type = self._extract_source_type(card_text)

            return {
                "source": self.source,
                "country": self.country,
                "currency": self.currency,
                "batch_id": self.batch_id,
                "make": make,
                "model": model,
                "year": year,
                "price": price,
                "url": url,
                "image_url": image_url,
                "location": location,
                "transmission": transmission,
                "body_type": body_type,
                "color": color,
                "is_imported": True if source_type == "Foreign Used" else (False if source_type == "Local Used" else None),
                "description": description[:500] if description else None,
            }

        except Exception as e:
            logger.debug(f"Basic parse error: {e}")
            return None

    def _scrape_detail_page(self, page, url: str) -> dict:
        detail = {
            "mileage": None,
            "mileage_unit": "km",
            "engine_size": None,
            "fuel_type": None,
            "drive_type": None,
            "seller_type": None,
            "trim": None,
            "body_type": None,
        }
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            
            
            try:
                show_more = page.query_selector("button:has-text('Show more'), button:has-text('Show More')")
                if show_more:
                    show_more.click()
                    page.wait_for_timeout(500)
            except:
                pass
            
            
            full_text = page.inner_text("body")
            
            
            html = page.content()
            
          
            mileage_patterns = [
                r'(\d{1,3}(?:,\d{3})+)\s*km',           # "139,284 km" or "139284 km"
                r'Mileage[:\s]+(\d{1,3}(?:,\d{3})+)',   # "Mileage: 139,284"
                r'([\d,]+)\s*(?:km|kilometers)',         # Any number before km
            ]
            for pattern in mileage_patterns:
                m = re.search(pattern, full_text, re.IGNORECASE)
                if m:
                    detail["mileage"] = float(m.group(1).replace(",", ""))
                    break
            
            
            engine_patterns = [
                r'(\d{3,4})\s*cc',                      # "1500cc" or "1500 cc"
                r'(\d+\.?\d*)\s*[Ll]\s*(?:engine| petrol| diesel)',  # "1.5L engine"
                r'Engine[:\s]+(\d{3,4})\s*cc',           # "Engine: 1500cc"
                r'(\d{3,4})\s*(?:cc|CC)',                # "1500cc" anywhere
            ]
            for pattern in engine_patterns:
                m = re.search(pattern, full_text, re.IGNORECASE)
                if m:
                    val = m.group(1)
                    if '.' in val:
                        # Convert liters to cc
                        detail["engine_size"] = str(int(float(val) * 1000))
                    else:
                        detail["engine_size"] = val
                    break
            
           
            fuel_patterns = [
                (r'\bPetrol\b', 'Petrol'),
                (r'\bDiesel\b', 'Diesel'),
                (r'\bHybrid\b', 'Hybrid'),
                (r'\bElectric\b', 'Electric'),
            ]
            for pattern, fuel in fuel_patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    detail["fuel_type"] = fuel
                    break
            
            
            drive_patterns = [
                (r'\b4WD\b|\b4x4\b', '4WD'),
                (r'\bAWD\b|\bAll Wheel\b', 'AWD'),
                (r'\b2WD\b|\bFWD\b|\bFront Wheel\b', '2WD'),
                (r'\bRWD\b|\bRear Wheel\b', 'RWD'),
            ]
            for pattern, drive in drive_patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    detail["drive_type"] = drive
                    break
            
            
            trim_match = re.search(r'Trim[:\s]+([^\n]+)', full_text, re.IGNORECASE)
            if trim_match:
                detail["trim"] = trim_match.group(1).strip()
            
            
            body_match = re.search(r'Body[:\s]+([^\n]+)', full_text, re.IGNORECASE)
            if body_match:
                detail["body_type"] = body_match.group(1).strip().title()
            
            
            if re.search(r'\bDealer\b', full_text, re.IGNORECASE):
                detail["seller_type"] = "Dealer"
            elif re.search(r'\bIndividual\b', full_text, re.IGNORECASE):
                detail["seller_type"] = "Individual"

        except Exception as e:
            logger.warning(f"Detail scrape failed for {url}: {e}")
        
        return detail

    def _extract_specs_from_table(self, page) -> dict:
        
        specs = {}
        
        try:
           
            rows = page.query_selector_all("""
                .b-advert-attributes__item, 
                [class*='attribute'],
                dl > div,
                tr,
                [class*='spec-row'],
                [class*='detail-row']
            """)
            
            for row in rows:
                try:
                   
                    key_el = (
                        row.query_selector("dt, .b-advert-attributes__key, [class*='key'], [class*='label'], th") 
                        or row.query_selector(":first-child")
                    )
                    val_el = (
                        row.query_selector("dd, .b-advert-attributes__value, [class*='value'], td")
                        or row.query_selector(":last-child")
                    )
                    
                    if key_el and val_el:
                        key = key_el.inner_text().strip().lower().replace(":", "").replace(" of manufacture", "")
                        val = val_el.inner_text().strip()
                        if key and val and val != "-":
                            specs[key] = val
                            
                except Exception:
                    continue
            
            # Approach B: We for text patterns if structured elements fail
            if not specs:
                html = page.content()
                text = page.inner_text("body")
                
               
                patterns = [
                    (r'(?:make|brand)[\s:]+([a-z]+)', 'make'),
                    (r'(?:model)[\s:]+([^\n]+)', 'model'),
                    (r'(?:year|year of manufacture)[\s:]+(\d{4})', 'year'),
                    (r'(?:trim)[\s:]+([^\n]+)', 'trim'),
                    (r'(?:body|body type)[\s:]+([^\n]+)', 'body'),
                    (r'(?:drivetrain|drive type)[\s:]+([^\n]+)', 'drivetrain'),
                    (r'(?:engine size|displacement)[\s:]+([\d,]+)\s*cc', 'engine size'),
                    (r'(?:fuel type|fuel)[\s:]+([^\n]+)', 'fuel type'),
                    (r'(?:mileage)[\s:]+([\d,]+)\s*km', 'mileage'),
                    (r'(?:seller type|seller)[\s:]+([^\n]+)', 'seller type'),
                ]
                
                for pattern, key in patterns:
                    m = re.search(pattern, text, re.IGNORECASE)
                    if m:
                        specs[key] = m.group(1).strip()

        except Exception as e:
            logger.debug(f"Specs extraction error: {e}")
        
        return specs

    def _get_description_text(self, page) -> str:
        
        try:
           
            selectors = [
                "[class*='description']",
                "[class*='desc']", 
                "[class*='about']",
                "[class*='details-text']",
                "article",
                ".b-advert__description"
            ]
            
            for sel in selectors:
                el = page.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if len(text) > 20:  # Must be substantial
                        return text
            
            
            return page.inner_text("body")[:2000]
            
        except Exception:
            return ""

    def _extract_price(self, text: str) -> float | None:
        match = re.search(r"KSh\s*([\d,]+)", text)
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    def _parse_url(self, href: str) -> tuple:
        location = make = model = year = color = body_type = None

        parts = href.strip("/").split("/")
        if parts and parts[0] != "cars":
            location = parts[0].replace("-", " ").title()

        car_part = parts[-1].replace(".html", "") if parts else ""
        car_part = re.sub(r'-[a-z0-9]{8,}$', '', car_part, flags=re.IGNORECASE)
        segments = car_part.split("-")

        body_types = {"sedan", "hatchback", "suv", "pickup", "van", "wagon", "coupe",
                      "minivan", "convertible", "truck", "bus"}
        colors = {"white", "black", "silver", "grey", "gray", "blue", "red", "green",
                  "yellow", "beige", "brown", "gold", "maroon", "pearl", "orange", "purple"}

        year_idx = None
        for i, seg in enumerate(segments):
            if _YEAR_RE.match(seg):
                year = int(seg)
                year_idx = i
                break

        if year_idx is not None and year_idx > 0:
            make = segments[0].lower()
            model_parts = segments[1:year_idx]
            
            if make == "land" and model_parts:
                if model_parts[0].lower() in ("cruiser", "rover"):
                    make = f"Land {model_parts.pop(0).title()}"
            
            model = " ".join(model_parts).title() if model_parts else None
            
        elif segments:
            make = segments[0].lower()
            model = " ".join(segments[1:]).title() if len(segments) > 1 else None

        for seg in segments:
            seg_lower = seg.lower()
            if seg_lower in colors and not color:
                color = seg.capitalize()
            if seg_lower in body_types and not body_type:
                body_type = seg.capitalize()

        return location, make, model, year, color, body_type

    def _extract_transmission(self, text: str) -> str | None:
        if re.search(r"\bAutomatic\b", text, re.IGNORECASE):
            return "Automatic"
        if re.search(r"\bManual\b", text, re.IGNORECASE):
            return "Manual"
        return None

    def _extract_source_type(self, text: str) -> str | None:
        if re.search(r"Foreign\s*Used", text, re.IGNORECASE):
            return "Foreign Used"
        if re.search(r"Local\s*Used", text, re.IGNORECASE):
            return "Local Used"
        return None