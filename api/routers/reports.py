# api/routers/reports.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional

from api.dependencies import get_db
from api.schemas import DealSummary

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/top-deals", response_model=List[DealSummary])
def top_deals(
    make: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get top import savings opportunities."""
    
    where = "cl.is_import = true"
    params = {"limit": limit}
    
    if make:
        where += " AND cl.make = :make"
        params["make"] = make
    
    query = f"""
    WITH matches AS (
        SELECT 
            cl.make, cl.model, cl.year,
            ic.total_landed_cost_kes as import_cost,
            c2.price_kes as local_price,
            c2.price_kes - ic.total_landed_cost_kes as savings_kes
        FROM cleaned_listings cl
        JOIN import_costs ic ON cl.id = ic.cleaned_id
        JOIN cleaned_listings c2 
            ON cl.make = c2.make AND cl.year = c2.year AND c2.is_import = false
        WHERE {where}
          AND (cl.model ILIKE '%' || c2.model || '%' OR c2.model ILIKE '%' || cl.model || '%')
    )
    SELECT make, model, year, import_cost, local_price, savings_kes,
           ROUND((savings_kes / import_cost * 100)::numeric, 1) as savings_pct
    FROM matches
    WHERE savings_kes > 0
    ORDER BY savings_kes DESC
    LIMIT :limit
    """
    
    result = db.execute(text(query), params)
    rows = result.mappings().all()
    return [dict(r) for r in rows]


@router.get("/by-make")
def stats_by_make(db: Session = Depends(get_db)):
    """Get aggregated stats by make."""
    
    query = """
        SELECT 
            make,
            COUNT(*) as total_listings,
            AVG(price_usd) as avg_price,
            MIN(price_usd) as min_price,
            MAX(price_usd) as max_price
        FROM cleaned_listings
        GROUP BY make
        ORDER BY total_listings DESC
    """
    
    result = db.execute(text(query))
    return [dict(r) for r in result.mappings().all()]