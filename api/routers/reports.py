# api/routers/reports.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from pydantic import BaseModel

from api.dependencies import get_db

router = APIRouter(prefix="/reports", tags=["reports"])



class DealResult(BaseModel):
    make: str
    model: str
    year: int
    import_cost: str          
    local_price: str          
    savings: str              
    savings_pct: str         
    verdict: str             


class MakeStats(BaseModel):
    make: str
    total_listings: int
    avg_price_usd: str        
    min_price_usd: str       
    max_price_usd: str        




def _kes(value) -> str:
    return f"KSh {round(float(value)):,}"

def _usd(value) -> str:
    return f"${round(float(value)):,}"

def _pct(value) -> str:
    return f"{round(float(value), 1)}%"




@router.get("/top-deals", response_model=List[DealResult])
def top_deals(
    make: Optional[str] = Query(None, description="Filter by make e.g. Toyota"),
    min_savings_pct: Optional[float] = Query(
        None, description="Only show deals with at least this % saving e.g. 10"
    ),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    
    where = ["cl.is_import = true"]
    params: dict = {"limit": limit}

    if make:
        where.append("cl.make ILIKE :make")
        params["make"] = f"%{make.strip()}%"

    if min_savings_pct is not None:
        where.append(
            "ROUND(((c2.price_kes - ic.total_landed_cost_kes) "
            "/ NULLIF(ic.total_landed_cost_kes, 0) * 100)::numeric, 1) >= :min_pct"
        )
        params["min_pct"] = min_savings_pct

    where_clause = " AND ".join(where)

    query = f"""
    WITH matches AS (
        SELECT
            cl.make,
            cl.model,
            cl.year,
            ROUND(ic.total_landed_cost_kes::numeric, 0)   AS import_cost_kes,
            ROUND(c2.price_kes::numeric, 0)                AS local_price_kes,
            ROUND((c2.price_kes - ic.total_landed_cost_kes)::numeric, 0)
                                                           AS savings_kes,
            ROUND(
                ((c2.price_kes - ic.total_landed_cost_kes)
                 / NULLIF(ic.total_landed_cost_kes, 0) * 100)::numeric, 1
            )                                              AS savings_pct
        FROM cleaned_listings cl
        JOIN import_costs ic ON cl.id = ic.cleaned_id
        JOIN cleaned_listings c2
            ON  cl.make = c2.make
            AND cl.year = c2.year
            AND c2.is_import = false
            AND (
                cl.model ILIKE '%' || c2.model || '%'
                OR c2.model ILIKE '%' || cl.model || '%'
            )
        WHERE {where_clause}
          AND c2.price_kes > ic.total_landed_cost_kes
    )
    SELECT *
    FROM matches
    ORDER BY savings_kes DESC
    LIMIT :limit
    """

    rows = db.execute(text(query), params).mappings().all()

    output = []
    for r in rows:
        savings_kes = float(r["savings_kes"])
        savings_pct = float(r["savings_pct"])
        output.append(DealResult(
            make        = r["make"],
            model       = r["model"].title(),
            year        = r["year"],
            import_cost = _kes(r["import_cost_kes"]),
            local_price = _kes(r["local_price_kes"]),
            savings     = _kes(savings_kes),
            savings_pct = _pct(savings_pct),
            verdict     = f"Import saves {_kes(savings_kes)} ({_pct(savings_pct)})",
        ))

    return output


@router.get("/by-make", response_model=List[MakeStats])
def stats_by_make(
    is_import: Optional[bool] = Query(
        None, description="true = Japan, false = Kenya, omit = all"
    ),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    where = ["1=1"]
    params: dict = {"limit": limit}

    if is_import is not None:
        where.append("is_import = :is_import")
        params["is_import"] = is_import

    result = db.execute(text(f"""
        SELECT
            make,
            COUNT(*)                              AS total_listings,
            ROUND(AVG(price_usd)::numeric, 0)     AS avg_price_usd,
            ROUND(MIN(price_usd)::numeric, 0)     AS min_price_usd,
            ROUND(MAX(price_usd)::numeric, 0)     AS max_price_usd
        FROM cleaned_listings
        WHERE {" AND ".join(where)}
        GROUP BY make
        ORDER BY total_listings DESC
        LIMIT :limit
    """), params)

    return [
        MakeStats(
            make           = r["make"],
            total_listings = r["total_listings"],
            avg_price_usd  = _usd(r["avg_price_usd"]),
            min_price_usd  = _usd(r["min_price_usd"]),
            max_price_usd  = _usd(r["max_price_usd"]),
        )
        for r in result.mappings().all()
    ]