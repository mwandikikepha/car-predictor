# app/cleaning.py

import json
import re
import hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter
import logging
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

USD_TO_KES = settings.USD_TO_KES
MIN_YEAR   = settings.MIN_YEAR
MAX_YEAR   = settings.MAX_YEAR


MAKE_NORMALIZE = {
    "toyota": "Toyota", "honda": "Honda", "nissan": "Nissan",
    "mazda": "Mazda", "subaru": "Subaru", "mitsubishi": "Mitsubishi",
    "suzuki": "Suzuki", "daihatsu": "Daihatsu", "isuzu": "Isuzu",
    "lexus": "Lexus", "infiniti": "Infiniti", "jeep": "Jeep",
    "mercedes-benz": "Mercedes-Benz", "mercedes": "Mercedes-Benz",
    "benz": "Mercedes-Benz", "bmw": "BMW",
    "volkswagen": "Volkswagen", "vw": "Volkswagen",
    "land rover": "Land Rover", "land-rover": "Land Rover",
    "mini": "MINI", "volvo": "Volvo", "ford": "Ford",
    "hyundai": "Hyundai", "kia": "Kia", "peugeot": "Peugeot",
    "audi": "Audi",
}

FUEL_NORMALIZE = {
    "hybrid(petrol)": "Hybrid", "hybrid(diesel)": "Hybrid",
    "hybrid": "Hybrid", "petrol": "Petrol", "gasoline": "Petrol",
    "diesel": "Diesel", "electric": "Electric", "ev": "Electric",
    "lpg": "LPG", "cng": "CNG", "plug-in hybrid": "Plug-in Hybrid",
}

TRANS_NORMALIZE = {
    "automatic": "Automatic", "auto": "Automatic", "at": "Automatic",
    "manual": "Manual", "mt": "Manual",
    "cvt": "CVT", "amt": "Semi-Automatic", "semi-automatic": "Semi-Automatic",
}



def prepare_cleaned_dir():
    cleaned_dir = Path("data/cleaned")
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    for f in cleaned_dir.glob("*.json"):
        f.unlink()
    logger.info("data/cleaned cleared for fresh run")


def load_raw_data(raw_dir: Path = Path("data/raw")) -> list[dict]:
    listings = []
    for json_file in raw_dir.glob("*.json"):
        if "summary" in json_file.name:
            continue
        logger.info(f"Loading {json_file.name}")
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "listings" in data:
            listings.extend(data["listings"])
        elif isinstance(data, list):
            listings.extend(data)
    logger.info(f"Total raw listings loaded: {len(listings)}")
    return listings



def normalize_make(make: str | None) -> str | None:
    if not make:
        return None
    return MAKE_NORMALIZE.get(make.lower().strip(), make.strip().title())


def normalize_fuel(fuel: str | None) -> str | None:
    if not fuel:
        return None
    return FUEL_NORMALIZE.get(fuel.lower().strip(), fuel.strip().title())


def normalize_transmission(trans: str | None) -> str | None:
    if not trans:
        return None
    return TRANS_NORMALIZE.get(trans.lower().strip(), trans.strip().title())




def generate_id(listing: dict) -> str:
   
    make     = listing.get("make", "unknown")
    model    = listing.get("model", "unknown")
    year     = listing.get("year", 0)
    source   = listing.get("source", "unknown")
    price    = listing.get("price_usd") or listing.get("price_original") or 0
    mileage  = listing.get("mileage_km") or 0

    clean_model = re.sub(r"[^a-zA-Z0-9]", "", str(model)).lower()[:20]
    base = f"{source}-{make}-{clean_model}-{year}-{price}-{mileage}"

    hash_suffix = hashlib.md5(base.encode()).hexdigest()[:8]
    return f"{source}-{make}-{clean_model}-{year}-{hash_suffix}"




def clean_listing(raw: dict) -> dict | None:
    year = raw.get("year")

    
    if not year or not isinstance(year, int):
        return None
    if not (MIN_YEAR <= year <= MAX_YEAR):
        return None

    
    make  = normalize_make(raw.get("make"))
    model = raw.get("model")
    if not make or not model:
        return None

   
    engine_size_cc = None
    engine_raw = raw.get("engine_size")
    if engine_raw:
        digits = "".join(c for c in str(engine_raw) if c.isdigit())
        if digits:
            engine_size_cc = int(digits)

    mileage_km = raw.get("mileage")

  
    price_original    = raw.get("price")
    original_currency = raw.get("currency", "USD").upper()

    if original_currency in ("USD", "US$"):
        price_usd = price_original
        price_kes = price_original * USD_TO_KES if price_original else None
    elif original_currency in ("KES", "KSH"):
        price_kes = price_original
        price_usd = price_original / USD_TO_KES if price_original else None
    else:
        price_usd = price_original
        price_kes = price_original * USD_TO_KES if price_original else None

    if not price_usd:
        return None

    price_per_km = (
        price_usd / mileage_km
        if mileage_km and mileage_km > 0
        else None
    )

    car_age = datetime.now().year - year

    cleaned = {
        "_id":               None,          # filled below
        "source":            raw.get("source", "unknown"),
        "make":              make,
        "model":             model,
        "year":              year,
        "price_usd":         price_usd,
        "price_kes":         price_kes,
        "price_original":    price_original,
        "original_currency": original_currency,
        "mileage_km":        mileage_km,
        "engine_size_cc":    engine_size_cc,
        "fuel_type":         normalize_fuel(raw.get("fuel_type")),
        "transmission":      normalize_transmission(raw.get("transmission")),
        "drive_type":        raw.get("drive_type"),
        "car_age":           car_age,
        "price_per_km":      price_per_km,
        "is_import":         raw.get("country") == "japan",
    }

    cleaned["_id"] = generate_id(cleaned)
    return cleaned




def clean_all(
    raw_dir:     Path = Path("data/raw"),
    cleaned_dir: Path = Path("data/cleaned"),
) -> list[dict]:
    prepare_cleaned_dir()

    raw_listings = load_raw_data(raw_dir)

    cleaned_listings: list[dict] = []
    seen_ids: set[str] = set()
    skipped = 0

    for raw in raw_listings:
        cleaned = clean_listing(raw)
        if not cleaned:
            skipped += 1
            continue

        if cleaned["_id"] in seen_ids:
            skipped += 1
            continue
        seen_ids.add(cleaned["_id"])

        cleaned_listings.append(cleaned)

    
    output_file = cleaned_dir / f"cleaned_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "cleaned_at":              datetime.now().isoformat(),
                "min_year":                MIN_YEAR,
                "max_year":                MAX_YEAR,
                "exchange_rate_usd_to_kes": USD_TO_KES,
                "count":                   len(cleaned_listings),
                "skipped":                 skipped,
                "listings":                cleaned_listings,
            },
            f,
            indent=2,
            default=str,
        )

    logger.info(f"Year filter applied: {MIN_YEAR}–{MAX_YEAR}")
    logger.info(f"Exchange rate used:  1 USD = {USD_TO_KES} KES")
    logger.info(f"Cleaned listings:    {len(cleaned_listings)}")
    logger.info(f"Skipped:             {skipped}")
    logger.info(f"Saved to:            {output_file}")

    sources = Counter(l["source"] for l in cleaned_listings)
    logger.info("By source:")
    for src, cnt in sources.most_common():
        logger.info(f"  {src}: {cnt}")

    years = Counter(l["year"] for l in cleaned_listings)
    logger.info("By year:")
    for yr, cnt in sorted(years.items()):
        logger.info(f"  {yr}: {cnt}")

    makes = Counter(l["make"] for l in cleaned_listings if l.get("make"))
    logger.info("Top makes:")
    for mk, cnt in makes.most_common(10):
        logger.info(f"  {mk}: {cnt}")

    imports = sum(1 for l in cleaned_listings if l.get("is_import"))
    local   = len(cleaned_listings) - imports
    logger.info(f"Import vs Local: {imports} import, {local} local")

    return cleaned_listings


if __name__ == "__main__":
    clean_all()