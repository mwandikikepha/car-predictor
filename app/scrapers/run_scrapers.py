# run_scrapers.py

import logging
import json
from pathlib import Path
from datetime import datetime

import sys


project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from japan_sbt import SBTJapanScraper
from japan_beforward import BeforwardScraper
from kenya_jiji import JijiKenyaScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

def prepare_raw_dir():
    raw_dir = Path("data/raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    # Delete old JSONs
    for f in raw_dir.glob("*.json"):
        f.unlink()
    
    logger.info("data/raw cleared for fresh run")

def run_all():
    
    prepare_raw_dir() 
    results = {
        "run_at": datetime.now().isoformat(),
        "scrapers": {}
    }

    scrapers = [
        ("sbt_japan", SBTJapanScraper(), 200),
        ("beforward_japan", BeforwardScraper(), 200),
        ("jiji_kenya", JijiKenyaScraper(), 120),
    ]

    for name, scraper, pages in scrapers:
        logger.info(f"Starting {name} ({pages} pages)...")
        try:
            listings = scraper.run(pages=pages)
            results["scrapers"][name] = {
                "status": "success",
                "listings": len(listings),
                "batch_id": scraper.batch_id,
            }
            logger.info(f"{name}: {len(listings)} listings saved")
        except Exception as e:
            results["scrapers"][name] = {
                "status": "failed",
                "error": str(e),
            }
            logger.error(f"{name} failed: {e}")

    # Save run summary
    summary_path = Path("data/raw") / f"run_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Run summary saved to {summary_path}")
    return results


if __name__ == "__main__":
    run_all()