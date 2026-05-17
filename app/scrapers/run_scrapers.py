# run_scrapers.py

import logging
import json
from pathlib import Path
from datetime import datetime

from japan_sbt import SBTJapanScraper
from japan_beforward import BeforwardScraper
from kenya_jiji import JijiKenyaScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def run_all():
    """Run all scrapers and collect results."""
    results = {
        "run_at": datetime.now().isoformat(),
        "scrapers": {}
    }

    scrapers = [
        ("sbt_japan", SBTJapanScraper(), 5),
        ("beforward_japan", BeforwardScraper(), 5),
        ("jiji_kenya", JijiKenyaScraper(), 10),
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