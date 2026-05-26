# api/routers/cars.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional

from api.dependencies import get_db
from api.schemas import CarResponse

router = APIRouter(prefix="/cars", tags=["cars"])




@router.get("/makes", response_model=List[str])
def get_makes(
    is_import: Optional[bool] = Query(
        None,
        description="True = Japan listings, False = Kenya listings, omit = all"
    ),
    db: Session = Depends(get_db),
):
    
    where = []
    params: dict = {}

    if is_import is not None:
        where.append("is_import = :is_import")
        params["is_import"] = is_import

    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    result = db.execute(
        text(f"""
            SELECT DISTINCT make
            FROM cleaned_listings
            {where_clause}
            ORDER BY make
        """),
        params,
    )
    return [row.make for row in result if row.make]


@router.get("/models", response_model=List[str])
def get_models(
    make: Optional[str] = Query(None, description="Filter models by make"),
    is_import: Optional[bool] = Query(None, description="True = Japan, False = Kenya"),
    db: Session = Depends(get_db),
):
    """Unique models for a given make, optionally scoped to import or local."""
    where = ["1=1"]
    params: dict = {}

    if make:
        where.append("make ILIKE :make")
        params["make"] = make
    if is_import is not None:
        where.append("is_import = :is_import")
        params["is_import"] = is_import

    result = db.execute(
        text(f"""
            SELECT DISTINCT model
            FROM cleaned_listings
            WHERE {" AND ".join(where)}
            ORDER BY model
        """),
        params,
    )
    return [row.model for row in result if row.model]


@router.get("/years", response_model=List[int])
def get_years(
    make: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    is_import: Optional[bool] = Query(None, description="True = Japan, False = Kenya"),
    db: Session = Depends(get_db),
):
    """Available years, optionally filtered by make / model / source."""
    where = ["1=1"]
    params: dict = {}

    if make:
        where.append("make ILIKE :make")
        params["make"] = make
    if model:
        where.append("model ILIKE :model")
        params["model"] = f"%{model}%"
    if is_import is not None:
        where.append("is_import = :is_import")
        params["is_import"] = is_import

    result = db.execute(
        text(f"""
            SELECT DISTINCT year
            FROM cleaned_listings
            WHERE {" AND ".join(where)}
            ORDER BY year DESC
        """),
        params,
    )
    return [row.year for row in result]


@router.get("/fuel-types", response_model=List[str])
def get_fuel_types(
    is_import: Optional[bool] = Query(None, description="True = Japan, False = Kenya"),
    db: Session = Depends(get_db),
):
    """Unique fuel types for dropdown."""
    where = ["fuel_type IS NOT NULL"]
    params: dict = {}

    if is_import is not None:
        where.append("is_import = :is_import")
        params["is_import"] = is_import

    result = db.execute(
        text(f"""
            SELECT DISTINCT fuel_type
            FROM cleaned_listings
            WHERE {" AND ".join(where)}
            ORDER BY fuel_type
        """),
        params,
    )
    return [row.fuel_type for row in result if row.fuel_type]


@router.get("/transmissions", response_model=List[str])
def get_transmissions(
    is_import: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """Unique transmission types for dropdown."""
    where = ["transmission IS NOT NULL"]
    params: dict = {}

    if is_import is not None:
        where.append("is_import = :is_import")
        params["is_import"] = is_import

    result = db.execute(
        text(f"""
            SELECT DISTINCT transmission
            FROM cleaned_listings
            WHERE {" AND ".join(where)}
            ORDER BY transmission
        """),
        params,
    )
    return [row.transmission for row in result if row.transmission]


@router.get("/stats/summary")
def get_summary_stats(db: Session = Depends(get_db)):
    """
    High-level counts for the dashboard header:
    total listings, Japan count, Kenya count, make count, year range.
    """
    result = db.execute(text("""
        SELECT
            COUNT(*)                                        AS total_listings,
            COUNT(*) FILTER (WHERE is_import = true)       AS japan_listings,
            COUNT(*) FILTER (WHERE is_import = false)      AS kenya_listings,
            COUNT(DISTINCT make)                            AS unique_makes,
            MIN(year)                                       AS year_min,
            MAX(year)                                       AS year_max,
            ROUND(AVG(price_usd) FILTER (WHERE is_import = true)::numeric,  0) AS avg_japan_price_usd,
            ROUND(AVG(price_usd) FILTER (WHERE is_import = false)::numeric, 0) AS avg_kenya_price_usd
        FROM cleaned_listings
    """))
    row = result.mappings().first()
    return dict(row) if row else {}


@router.get("/stats/by-make")
def stats_by_make(
    is_import: Optional[bool] = Query(None, description="Scope to Japan or Kenya"),
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """
    Per-make statistics: listing count, avg/min/max price.
    Useful for bar charts on the dashboard.
    """
    where = ["1=1"]
    params: dict = {"limit": limit}

    if is_import is not None:
        where.append("is_import = :is_import")
        params["is_import"] = is_import

    result = db.execute(
        text(f"""
            SELECT
                make,
                COUNT(*)                          AS total_listings,
                ROUND(AVG(price_usd)::numeric, 0) AS avg_price_usd,
                ROUND(MIN(price_usd)::numeric, 0) AS min_price_usd,
                ROUND(MAX(price_usd)::numeric, 0) AS max_price_usd
            FROM cleaned_listings
            WHERE {" AND ".join(where)}
            GROUP BY make
            ORDER BY total_listings DESC
            LIMIT :limit
        """),
        params,
    )
    return [dict(r) for r in result.mappings().all()]



@router.get("/", response_model=List[CarResponse])
def list_cars(
    make: Optional[str] = Query(None, description="Filter by make (exact, case-insensitive)"),
    model: Optional[str] = Query(None, description="Filter by model (ILIKE partial match)"),
    year: Optional[int] = Query(None, description="Exact year"),
    year_min: Optional[int] = Query(None, description="Year range lower bound"),
    year_max: Optional[int] = Query(None, description="Year range upper bound"),
    fuel_type: Optional[str] = Query(None),
    transmission: Optional[str] = Query(None),
    is_import: Optional[bool] = Query(
        None, description="True = Japan listings, False = Kenya listings"
    ),
    price_min: Optional[float] = Query(None, description="Minimum price in USD"),
    price_max: Optional[float] = Query(None, description="Maximum price in USD"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    
    where = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if make:
        where.append("make ILIKE :make")
        params["make"] = make
    if model:
        where.append("model ILIKE :model")
        params["model"] = f"%{model}%"
    if year:
        where.append("year = :year")
        params["year"] = year
    if year_min:
        where.append("year >= :year_min")
        params["year_min"] = year_min
    if year_max:
        where.append("year <= :year_max")
        params["year_max"] = year_max
    if fuel_type:
        where.append("fuel_type ILIKE :fuel_type")
        params["fuel_type"] = fuel_type
    if transmission:
        where.append("transmission ILIKE :transmission")
        params["transmission"] = transmission
    if is_import is not None:
        where.append("is_import = :is_import")
        params["is_import"] = is_import
    if price_min is not None:
        where.append("price_usd >= :price_min")
        params["price_min"] = price_min
    if price_max is not None:
        where.append("price_usd <= :price_max")
        params["price_max"] = price_max

    result = db.execute(
        text(f"""
            SELECT
                id, _id, source, make, model, year,
                price_usd, price_kes,
                mileage_km, engine_size_cc,
                fuel_type, transmission, drive_type, is_import
            FROM cleaned_listings
            WHERE {" AND ".join(where)}
            ORDER BY year DESC, price_usd ASC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    return [dict(r) for r in result.mappings().all()]




@router.get("/{car_id}", response_model=CarResponse)
def get_car(car_id: int, db: Session = Depends(get_db)):
    
    result = db.execute(
        text("""
            SELECT
                id, _id, source, make, model, year,
                price_usd, price_kes,
                mileage_km, engine_size_cc,
                fuel_type, transmission, drive_type, is_import
            FROM cleaned_listings
            WHERE id = :car_id
        """),
        {"car_id": car_id},
    )
    row = result.mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"Car with id={car_id} not found")

    return dict(row)