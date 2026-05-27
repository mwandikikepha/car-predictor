# api/routers/reports.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from pydantic import BaseModel

from api.dependencies import get_db

router = APIRouter(prefix="/reports", tags=["reports"])

# Savings % above this are flagged — shown with a warning, not hidden.
MAX_CREDIBLE_SAVINGS_PCT = 80.0

# Minimum Kenya listings a make needs before the outlier filter activates.
MIN_LOCAL_LISTINGS_FOR_FILTER = 3

# Local listings priced above this multiple of the make's median are excluded.
# we useMedianso one bad listing can't skew the reference price.
OUTLIER_MEDIAN_MULTIPLIER = 2.5




class DealResult(BaseModel):
    make: str
    model: str
    year: int
    import_cost: str
    local_price: str
    savings: str
    savings_pct: str
    verdict: str
    data_quality: str        

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

def _format_deal(r: dict) -> DealResult:
    savings_kes = float(r["savings_kes"])
    savings_pct = float(r["savings_pct"])

    if savings_pct > MAX_CREDIBLE_SAVINGS_PCT:
        pct_display  = f">{MAX_CREDIBLE_SAVINGS_PCT:.0f}%"
        verdict      = (
            f"Import likely much cheaper — verify the local price "
            f"before deciding (estimated saving: {_kes(savings_kes)})"
        )
        data_quality = "check_local_price"
    else:
        pct_display  = _pct(savings_pct)
        verdict      = f"Import saves {_kes(savings_kes)} ({pct_display})"
        data_quality = "verified"

    return DealResult(
        make         = r["make"],
        model        = r["model"].strip().title(),
        year         = r["year"],
        import_cost  = _kes(r["import_cost_kes"]),
        local_price  = _kes(r["local_price_kes"]),
        savings      = _kes(savings_kes),
        savings_pct  = pct_display,
        verdict      = verdict,
        data_quality = data_quality,
    )




@router.get("/top-deals", response_model=List[DealResult])
def top_deals(
    make: Optional[str] = Query(None, description="Filter by make e.g. Toyota"),
    min_savings_pct: Optional[float] = Query(
        None, description="Only return deals saving at least this % e.g. 10"
    ),
    verified_only: bool = Query(
        False,
        description="If true, hide deals flagged as check_local_price"
    ),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):

    where = ["cl.is_import = true"]
    params: dict = {
        "limit":        limit,
        "min_listings": MIN_LOCAL_LISTINGS_FOR_FILTER,
        "multiplier":   OUTLIER_MEDIAN_MULTIPLIER,
    }

    if make:
        where.append("cl.make ILIKE :make")
        params["make"] = f"%{make.strip()}%"

    if min_savings_pct is not None:
        params["min_pct"] = min_savings_pct

    where_clause = " AND ".join(where)
    savings_pct_filter = (
        "AND deal_savings_pct >= :min_pct" if min_savings_pct is not None else ""
    )

    query = f"""
    WITH local_stats AS (
        -- Per-make median and count — median is robust to outliers.
        SELECT
            make,
            COUNT(*)                                     AS listing_count,
            PERCENTILE_CONT(0.5) WITHIN GROUP
                (ORDER BY price_kes)                     AS median_price
        FROM cleaned_listings
        WHERE is_import = false
          AND price_kes IS NOT NULL
        GROUP BY make
    ),

    raw_matches AS (
        -- All Japan cars matched to a credible local Kenya equivalent.
        SELECT
            cl.make,
            cl.model,
            cl.year,
            ic.total_landed_cost_kes                     AS import_cost_kes,
            c2.price_kes                                 AS local_price_kes,
            (c2.price_kes - ic.total_landed_cost_kes)    AS savings_kes,
            ((c2.price_kes - ic.total_landed_cost_kes)
             / NULLIF(ic.total_landed_cost_kes, 0) * 100) AS savings_pct_raw
        FROM cleaned_listings cl
        JOIN import_costs ic
            ON cl.id = ic.cleaned_id
        JOIN cleaned_listings c2
            ON  cl.make      = c2.make
            AND cl.year      = c2.year
            AND c2.is_import = false
            AND (
                cl.model ILIKE '%' || c2.model || '%'
                OR c2.model ILIKE '%' || cl.model || '%'
            )
        -- Outlier filter: only active when we have enough local data
        LEFT JOIN local_stats ls ON ls.make = c2.make
        WHERE {where_clause}
          AND c2.price_kes > ic.total_landed_cost_kes
          AND (
              -- Enough local data: apply median filter
              (ls.listing_count >= :min_listings
               AND c2.price_kes <= ls.median_price * :multiplier)
              OR
              -- Too few local listings: allow through, Python flags if >80%
              COALESCE(ls.listing_count, 0) < :min_listings
          )
    ),

    best_per_model AS (
        SELECT DISTINCT ON (make, model, year)
            make,
            model,
            year,
            ROUND(import_cost_kes::numeric, 0)    AS import_cost_kes,
            ROUND(local_price_kes::numeric, 0)    AS local_price_kes,
            ROUND(savings_kes::numeric, 0)        AS savings_kes,
            ROUND(savings_pct_raw::numeric, 1)    AS savings_pct
        FROM raw_matches
        ORDER BY make, model, year, import_cost_kes ASC
    )

    SELECT *
    FROM best_per_model
    WHERE savings_kes > 0
    {savings_pct_filter}
    ORDER BY savings_kes DESC
    LIMIT :limit
    """

    rows = db.execute(text(query), params).mappings().all()
    results = [_format_deal(dict(r)) for r in rows]

    if verified_only:
        results = [r for r in results if r.data_quality == "verified"]

    return results


@router.get("/top-deals/summary")
def top_deals_summary(
    make: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):

    params: dict = {
        "max_pct":      MAX_CREDIBLE_SAVINGS_PCT,
        "min_listings": MIN_LOCAL_LISTINGS_FOR_FILTER,
        "multiplier":   OUTLIER_MEDIAN_MULTIPLIER,
    }
    make_filter = ""
    if make:
        make_filter = "AND cl.make ILIKE :make"
        params["make"] = f"%{make.strip()}%"

    result = db.execute(text(f"""
        WITH local_stats AS (
            SELECT
                make,
                COUNT(*)                                     AS listing_count,
                PERCENTILE_CONT(0.5) WITHIN GROUP
                    (ORDER BY price_kes)                     AS median_price
            FROM cleaned_listings
            WHERE is_import = false AND price_kes IS NOT NULL
            GROUP BY make
        ),
        raw_matches AS (
            SELECT
                cl.make,
                cl.model,
                cl.year,
                (c2.price_kes - ic.total_landed_cost_kes)    AS savings_kes,
                ((c2.price_kes - ic.total_landed_cost_kes)
                 / NULLIF(ic.total_landed_cost_kes, 0) * 100) AS savings_pct_raw
            FROM cleaned_listings cl
            JOIN import_costs ic ON cl.id = ic.cleaned_id
            JOIN cleaned_listings c2
                ON  cl.make      = c2.make
                AND cl.year      = c2.year
                AND c2.is_import = false
                AND (
                    cl.model ILIKE '%' || c2.model || '%'
                    OR c2.model ILIKE '%' || cl.model || '%'
                )
            LEFT JOIN local_stats ls ON ls.make = c2.make
            WHERE cl.is_import = true
              {make_filter}
              AND c2.price_kes > ic.total_landed_cost_kes
              AND (
                  (ls.listing_count >= :min_listings
                   AND c2.price_kes <= ls.median_price * :multiplier)
                  OR COALESCE(ls.listing_count, 0) < :min_listings
              )
        ),
        best_per_model AS (
            SELECT DISTINCT ON (make, model, year)
                make, model, year,
                ROUND(savings_kes::numeric, 0)       AS savings_kes,
                ROUND(savings_pct_raw::numeric, 1)   AS savings_pct
            FROM raw_matches
            ORDER BY make, model, year, savings_kes DESC
        )
        SELECT
            COUNT(*)                            AS total_deals,
            ROUND(MAX(savings_kes)::numeric, 0) AS best_saving_kes,
            ROUND(AVG(savings_kes)::numeric, 0) AS avg_saving_kes,
            ROUND(MAX(savings_pct)::numeric, 1) AS best_saving_pct
        FROM best_per_model
        WHERE savings_pct <= :max_pct
    """), params)

    row = result.mappings().first()
    if not row or not row["total_deals"]:
        return {
            "total_deals":     0,
            "best_saving":     "—",
            "avg_saving":      "—",
            "best_saving_pct": "—",
        }

    return {
        "total_deals":     int(row["total_deals"]),
        "best_saving":     _kes(row["best_saving_kes"]),
        "avg_saving":      _kes(row["avg_saving_kes"]),
        "best_saving_pct": _pct(row["best_saving_pct"]),
    }


@router.get("/by-make", response_model=List[MakeStats])
def stats_by_make(
    is_import: Optional[bool] = Query(
        None, description="true = Japan, false = Kenya, omit = all"
    ),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Per-make statistics — listing counts and price ranges."""
    where = ["price_usd IS NOT NULL"]
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