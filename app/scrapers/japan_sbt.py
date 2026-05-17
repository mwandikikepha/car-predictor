# app/scrapers/japan_sbt.py

import re
from typing import Optional
from bs4 import BeautifulSoup
from base import BaseScraper

_TITLE_RE = re.compile(r'^(\d{4})(?:/\d{1,2})?\s+(\S+)\s+(.+)$')
_MILEAGE_RE = re.compile(r'([\d,]+)\s*km', re.IGNORECASE)
_ENGINE_RE = re.compile(r'([\d,]+)\s*cc', re.IGNORECASE)

FUEL_MAP = {
    "HYBRID(PETROL)": "Hybrid", "HYBRID(DIESEL)": "Hybrid",
    "HYBRID": "Hybrid", "PETROL": "Petrol", "GASOLINE": "Petrol",
    "DIESEL": "Diesel", "ELECTRIC": "Electric", "EV": "Electric",
    "LPG": "LPG", "CNG": "CNG", "PLUG-IN HYBRID": "Plug-in Hybrid",
}

TRANS_MAP = {
    "AT": "Automatic", "AUTO": "Automatic", "AUTOMATIC": "Automatic",
    "MT": "Manual", "MANUAL": "Manual",
    "CVT": "CVT", "AMT": "Semi-Automatic",
}

_TRANS_RE = re.compile(r'\d*(AT|MT|CVT|AMT)', re.IGNORECASE)

MAKE_MAP = {
    "TOYOTA": "Toyota", "HONDA": "Honda", "NISSAN": "Nissan",
    "MAZDA": "Mazda", "SUBARU": "Subaru", "MITSUBISHI": "Mitsubishi",
    "SUZUKI": "Suzuki", "DAIHATSU": "Daihatsu", "ISUZU": "Isuzu",
    "LEXUS": "Lexus", "INFINITI": "Infiniti", "HINO": "Hino",
    "BMW": "BMW", "MERCEDES-BENZ": "Mercedes-Benz",
    "MERCEDES": "Mercedes-Benz", "VOLKSWAGEN": "Volkswagen",
    "LAND": "Land Rover",
}


def _get_status(card, class_suffix: str) -> Optional[str]:
    for el in card.find_all(class_="card-product__status"):
        if class_suffix in (el.get("class") or []):
            val = el.get_text(strip=True)
            return val if val and val != "-" else None
    return None


class SBTJapanScraper(BaseScraper):
    source = "sbt_japan"
    base_url = "https://www.sbtjapan.com"
    country = "japan"
    currency = "USD"

    def scrape_listings(self, pages: int = 5) -> list[dict]:
        listings = []
        seen_urls = set()

        for page in range(1, pages + 1):
            url = f"{self.base_url}/used-cars/search?steering=RHD&page={page}"
            
            response = self._get(url)
            if response is None:
                break

            soup = self._parse_html(response)
            cards = soup.select(".card-product")

            if not cards:
                break

            for card in cards:
                try:
                    listing = self._parse_card(card)
                    if listing:
                        if listing.get("url") in seen_urls:
                            continue
                        seen_urls.add(listing["url"])
                        listings.append(listing)
                except Exception:
                    continue

            if len(cards) < 3:
                break

        return listings

    def _parse_card(self, card) -> Optional[dict]:
        try:
            link = card.select_one(".card-product__wrap")
            if not link:
                return None
            href = link.get("href", "")
            if not href:
                return None
            
            url = self.base_url + href
            stock_id = href.rstrip("/").split("/")[-1].upper()

            title_el = card.select_one(".card-product__product")
            if not title_el:
                return None
            
            year, make, model = self._parse_title(title_el.get_text(strip=True))
            if not make or not year:
                return None

            price_el = card.select_one(".card-product__price")
            if not price_el:
                return None
            
            price_text = price_el.get_text(strip=True).replace(",", "")
            try:
                price = float(price_text)
            except ValueError:
                return None

            data = {
                "source": self.source,
                "country": self.country,
                "currency": self.currency,
                "batch_id": self.batch_id,
                "url": url,
                "stock_id": stock_id,
                "make": make,
                "model": model,
                "year": year,
                "price": price,
            }

            mileage_raw = _get_status(card, "-mileage")
            if mileage_raw:
                m = _MILEAGE_RE.search(mileage_raw)
                if m:
                    data["mileage"] = int(m.group(1).replace(",", ""))
                    data["mileage_unit"] = "km"

            for el in card.find_all(class_="card-product__status"):
                if "-engine-capacity" not in (el.get("class") or []):
                    continue
                raw = el.get_text(strip=True)
                if raw and raw != "-":
                    m = _ENGINE_RE.search(raw)
                    if m:
                        data["engine_size"] = m.group(1).replace(",", "")
                        break

            trans_raw = _get_status(card, "-transmission")
            if trans_raw:
                m = _TRANS_RE.search(trans_raw.upper())
                suffix = m.group(1) if m else trans_raw.upper()
                data["transmission"] = TRANS_MAP.get(suffix, trans_raw.title())

            fuel_raw = _get_status(card, "-fuel-type")
            if fuel_raw:
                data["fuel_type"] = FUEL_MAP.get(fuel_raw.upper(), fuel_raw.title())

            drive_raw = _get_status(card, "-drive-type")
            if drive_raw:
                data["drive_type"] = drive_raw

            color_raw = _get_status(card, "-body-color")
            if color_raw:
                data["body_color"] = color_raw.title()

            doors_raw = _get_status(card, "-door")
            if doors_raw and doors_raw.isdigit():
                data["doors"] = int(doors_raw)

            return data

        except Exception:
            return None

    def _parse_title(self, raw: str) -> tuple:
        m = _TITLE_RE.match(raw.strip())
        if not m:
            return None, None, None
        
        year = int(m.group(1))
        make_raw = m.group(2).upper()
        model_raw = m.group(3).strip()

        if make_raw == "LAND" and model_raw.upper().startswith("ROVER"):
            make = "Land Rover"
            model_raw = model_raw[5:].strip()
        else:
            make = MAKE_MAP.get(make_raw, make_raw.title())

        model = model_raw.title()
        return year, make, model