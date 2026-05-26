# app/loader.py

import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session
from database.connection import engine
from database.models import CleanedListing
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Single source of truth: pulled from settings ──────────────────
MIN_YEAR = settings.MIN_YEAR
MAX_YEAR = settings.MAX_YEAR


def load_cleaned_data(cleaned_dir: Path = Path("data/cleaned")) -> list[dict]:
    """Load the most recently written cleaned JSON file."""
    json_files = list(cleaned_dir.glob("cleaned_*.json"))
    if not json_files:
        raise FileNotFoundError(
            "No cleaned files found in data/cleaned. Run cleaning.py first."
        )
    latest = max(json_files, key=lambda f: f.stat().st_mtime)
    logger.info(f"Loading {latest.name}")
    with open(latest, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("listings", [])


def clear_table(session: Session):
    session.query(CleanedListing).delete()
    session.commit()
    logger.info("cleaned_listings table truncated")


def insert_listings(session: Session, listings: list[dict]) -> tuple[int, int]:
    """
    Insert cleaned listings into the database.

    Validation here is intentionally minimal — cleaning.py owns the
    business rules.  The loader only enforces hard database constraints
    (required fields, year sanity check against settings) so that a
    misconfigured cleaning run cannot silently insert garbage.
    """
    count  = 0
    failed = 0
    failed_reasons: list[str] = []

    for listing in listings:
        uid = listing.get("_id", "unknown")

        if not listing.get("make"):
            failed += 1
            failed_reasons.append(f"{uid}: missing make")
            continue

        if not listing.get("model"):
            failed += 1
            failed_reasons.append(f"{uid}: missing model")
            continue

        year = listing.get("year")
        if not year or not (MIN_YEAR <= year <= MAX_YEAR):
            failed += 1
            failed_reasons.append(
                f"{uid}: year {year!r} outside allowed range "
                f"{MIN_YEAR}–{MAX_YEAR}"
            )
            continue

        if not listing.get("price_usd"):
            failed += 1
            failed_reasons.append(f"{uid}: missing price_usd")
            continue

        try:
            db_listing = CleanedListing(
                _id               = listing["_id"],
                source            = listing["source"],
                make              = listing["make"],
                model             = listing["model"],
                year              = listing["year"],
                price_usd         = listing.get("price_usd"),
                price_kes         = listing.get("price_kes"),
                price_original    = listing.get("price_original"),
                original_currency = listing.get("original_currency"),
                mileage_km        = listing.get("mileage_km"),
                engine_size_cc    = listing.get("engine_size_cc"),
                fuel_type         = listing.get("fuel_type"),
                transmission      = listing.get("transmission"),
                drive_type        = listing.get("drive_type"),
                car_age           = listing.get("car_age"),
                price_per_km      = listing.get("price_per_km"),
                is_import         = listing.get("is_import", True),
            )
            session.add(db_listing)
            count += 1

            if count % 100 == 0:
                session.commit()
                logger.info(f"Inserted {count} listings...")

        except Exception as e:
            failed += 1
            failed_reasons.append(f"{uid}: {str(e)[:100]}")
            session.rollback()
            continue

    session.commit()
    logger.info(f"Total inserted: {count}")
    logger.info(f"Total failed:   {failed}")

    if failed_reasons:
        logger.warning("First 10 failures:")
        for reason in failed_reasons[:10]:
            logger.warning(f"  {reason}")

    return count, failed


def run():
    logger.info(f"Year range enforced by loader: {MIN_YEAR}–{MAX_YEAR}")

    listings = load_cleaned_data()
    logger.info(f"Loaded {len(listings)} cleaned listings")

    with Session(engine) as session:
        clear_table(session)
        count, failed = insert_listings(session, listings)

    logger.info("Loader complete")
    return count, failed


if __name__ == "__main__":
    run()