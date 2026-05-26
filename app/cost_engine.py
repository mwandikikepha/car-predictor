# app/cost_engine.py

import logging
from datetime import datetime
import sys
from pathlib import Path
from sqlalchemy.orm import Session

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.connection import engine
from database.models import CleanedListing, ImportCost
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


USD_TO_KES = settings.USD_TO_KES

IMPORT_DUTY_RATE = 0.25  
EXCISE_DUTY_RATE = 0.20      
VAT_RATE = 0.16              
IDF_RATE = 0.035             
RDL_RATE = 0.02             


SHIPPING_USD = 1500.0       
INSURANCE_RATE = 0.015      
PORT_HANDLING_KES = 25000.0
CLEARING_AGENT_KES = 35000.0
REGISTRATION_KES = 15000.0
INSPECTION_KES = 20000.0
OTHER_FEES_KES = 10000.0


def calculate_cif(fob_price_usd: float) -> dict:
    insurance_usd = fob_price_usd * INSURANCE_RATE
    freight_usd = SHIPPING_USD
    cif_usd = fob_price_usd + insurance_usd + freight_usd
    
    return {
        "fob_price_usd": fob_price_usd,
        "insurance_usd": insurance_usd,
        "freight_usd": freight_usd,
        "cif_usd": cif_usd,
    }


def calculate_kra_taxes(cif_usd: float) -> dict:
    cif_kes = cif_usd * USD_TO_KES
    
    import_duty_kes = cif_kes * IMPORT_DUTY_RATE
    excise_duty_kes = (cif_kes + import_duty_kes) * EXCISE_DUTY_RATE
    vat_kes = (cif_kes + import_duty_kes + excise_duty_kes) * VAT_RATE
    idf_kes = cif_kes * IDF_RATE
    rdl_kes = cif_kes * RDL_RATE
    
    total_taxes_kes = import_duty_kes + excise_duty_kes + vat_kes + idf_kes + rdl_kes
    
    return {
        "import_duty_kes": import_duty_kes,
        "excise_duty_kes": excise_duty_kes,
        "vat_kes": vat_kes,
        "idf_kes": idf_kes,
        "rdl_kes": rdl_kes,
        "total_taxes_kes": total_taxes_kes,
    }


def calculate_other_costs() -> dict:
    return {
        "port_handling_kes": PORT_HANDLING_KES,
        "clearing_agent_kes": CLEARING_AGENT_KES,
        "registration_kes": REGISTRATION_KES,
        "inspection_kes": INSPECTION_KES,
        "other_fees_kes": OTHER_FEES_KES,
    }


def calculate_total_cost(fob_price_usd: float) -> dict:
    """Calculate full import cost breakdown."""
    cif = calculate_cif(fob_price_usd)
    taxes = calculate_kra_taxes(cif["cif_usd"])
    other = calculate_other_costs()
    
    total_landed_cost_kes = (
        cif["cif_usd"] * USD_TO_KES
        + taxes["total_taxes_kes"]
        + sum(other.values())
    )
    
    return {
        **cif,
        **taxes,
        **other,
        "total_landed_cost_kes": total_landed_cost_kes,
        "total_landed_cost_usd": total_landed_cost_kes / USD_TO_KES,
        "usd_to_kes": USD_TO_KES,
    }


def process_all_imports():
    """Calculate costs for all Japan listings and save to DB."""
    with Session(engine) as session:
        # Get Japan listings
        japan_listings = session.query(CleanedListing).filter(
            CleanedListing.is_import == True
        ).all()
        
        logger.info(f"Processing {len(japan_listings)} Japan listings")
        
        session.query(ImportCost).delete()
        session.commit()
        logger.info("Cleared old import costs")
        
        count = 0
        for listing in japan_listings:
            if not listing.price_usd:
                continue
            
            try:
                costs = calculate_total_cost(listing.price_usd)
                
                import_cost = ImportCost(
                    cleaned_id=listing.id,
                    calculated_at=datetime.now(),
                    **costs
                )
                
                session.add(import_cost)
                count += 1
                
                if count % 100 == 0:
                    session.commit()
                    logger.info(f"Processed {count} listings...")
                    
            except Exception as e:
                logger.warning(f"Failed for {listing._id}: {e}")
                session.rollback()
                continue
        
        session.commit()
        logger.info(f"Total import costs calculated: {count}")


if __name__ == "__main__":
    process_all_imports()