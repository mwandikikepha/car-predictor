# app/loader.py

import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from sqlalchemy.orm import Session
from database.connection import engine
from database.models import CleanedListing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def load_cleaned_data(cleaned_dir: Path = Path("data/cleaned")) -> list[dict]:
    """Load the latest cleaned JSON file."""
    json_files = list(cleaned_dir.glob("cleaned_*.json"))
    if not json_files:
        raise FileNotFoundError("No cleaned files found")
    
    latest = max(json_files, key=lambda f: f.stat().st_mtime)
    logger.info(f"Loading {latest.name}")
    
    with open(latest, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return data.get("listings", [])


def clear_table(session: Session):
    """Truncate cleaned_listings table."""
    session.query(CleanedListing).delete()
    session.commit()
    logger.info("cleaned_listings table truncated")


def insert_listings(session: Session, listings: list[dict]):
    """Insert listings into database with validation."""
    count = 0
    failed = 0
    failed_reasons = []
    
    for listing in listings:
        # Pre-validate required fields
        if not listing.get("make"):
            failed += 1
            failed_reasons.append(f"{listing.get('_id', 'unknown')}: missing make")
            continue
            
        if not listing.get("model"):
            failed += 1
            failed_reasons.append(f"{listing.get('_id', 'unknown')}: missing model")
            continue
            
        year = listing.get("year")
        if not year or not (2010 <= year <= 2026):
            failed += 1
            failed_reasons.append(f"{listing.get('_id', 'unknown')}: invalid year={year}")
            continue
        
        try:
            db_listing = CleanedListing(
                _id=listing["_id"],
                source=listing["source"],
                make=listing["make"],
                model=listing["model"],
                year=listing["year"],
                price_usd=listing.get("price_usd"),
                price_kes=listing.get("price_kes"),
                price_original=listing.get("price_original"),
                original_currency=listing.get("original_currency"),
                mileage_km=listing.get("mileage_km"),
                engine_size_cc=listing.get("engine_size_cc"),
                fuel_type=listing.get("fuel_type"),
                transmission=listing.get("transmission"),
                drive_type=listing.get("drive_type"),
                car_age=listing.get("car_age"),
                price_per_km=listing.get("price_per_km"),
                is_import=listing.get("is_import", True),
            )
            session.add(db_listing)
            count += 1
            
            if count % 100 == 0:
                session.commit()
                logger.info(f"Inserted {count} listings...")
                
        except Exception as e:
            failed += 1
            failed_reasons.append(f"{listing.get('_id', 'unknown')}: {str(e)[:80]}")
            session.rollback()
            continue
    
    session.commit()
    logger.info(f"Total inserted: {count}")
    logger.info(f"Total failed: {failed}")
    
    if failed_reasons:
        logger.warning(f"First 10 failures:")
        for reason in failed_reasons[:10]:
            logger.warning(f"  {reason}")
    
    return count, failed


def run():
    """Main loader: clear table, load cleaned data, insert."""
    listings = load_cleaned_data()
    logger.info(f"Loaded {len(listings)} cleaned listings")
    
    with Session(engine) as session:
        clear_table(session)
        count, failed = insert_listings(session, listings)
    
    logger.info("Loader complete")
    return count, failed


if __name__ == "__main__":
    run()