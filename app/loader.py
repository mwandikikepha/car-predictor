# loader.py

import json
import logging
from pathlib import Path
from datetime import datetime
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

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
    """Insert listings into database."""
    count = 0
    for listing in listings:
        try:
            db_listing = CleanedListing(
                _id=listing["_id"],
                batch_id=listing.get("batch_id", "unknown"),
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
                body_type=listing.get("body_type"),
                color=listing.get("body_color"),  # body_color → color
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
            logger.warning(f"Failed to insert {listing.get('_id')}: {e}")
            session.rollback()
            continue
    
    session.commit()
    logger.info(f"Total inserted: {count}")


def run():
    listings = load_cleaned_data()
    logger.info(f"Loaded {len(listings)} cleaned listings")
    
    with Session(engine) as session:
        clear_table(session)
        insert_listings(session, listings)
    
    logger.info("Loader complete")


if __name__ == "__main__":
    run()