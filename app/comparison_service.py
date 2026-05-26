# app/comparison_service.py


from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text


def get_comparisons(
    db: Session,
    make: Optional[str] = None,
    model: Optional[str] = None,
    year: Optional[int] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    engine_size_cc: Optional[int] = None,
    fuel_type: Optional[str] = None,
    mileage_km_max: Optional[int] = None,
    transmission: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    
    
    japan_conditions = ["cl.is_import = true"]
    params: dict = {
        "year":         year,
        "year_minus":   year - 1 if year else None,
        "year_plus":    year + 1 if year else None,
        "engine_size":  engine_size_cc,
        "engine_min":   int(engine_size_cc * 0.9) if engine_size_cc else None,
        "engine_max":   int(engine_size_cc * 1.1) if engine_size_cc else None,
        "fuel_type":    f"%{fuel_type.strip()}%" if fuel_type else "%",
        "transmission": f"%{transmission.strip()}%" if transmission else "%",
        "mileage_max":  mileage_km_max,
        "limit":        limit,
        "offset":       offset,
    }

    if make:
        japan_conditions.append("cl.make ILIKE :make")
        params["make"] = f"%{make.strip()}%"
    else:
        params["make"] = "%"
        japan_conditions.append("cl.make ILIKE :make")

    if model:
        japan_conditions.append("cl.model ILIKE :model")
        params["model"] = f"%{model.strip()}%"
    else:
        params["model"] = "%"
        japan_conditions.append("cl.model ILIKE :model")

    if year_min:
        japan_conditions.append("cl.year >= :year_min")
        params["year_min"] = year_min
    if year_max:
        japan_conditions.append("cl.year <= :year_max")
        params["year_max"] = year_max

    japan_where = " AND ".join(japan_conditions)

    query = f"""
    WITH japan_cars AS (
        SELECT
            cl.id,
            cl.make,
            cl.model,
            cl.year,
            cl.engine_size_cc,
            cl.mileage_km,
            cl.fuel_type,
            cl.transmission,
            cl.drive_type,
            ic.fob_price_usd,
            ic.total_landed_cost_kes  AS import_cost_kes,
            ic.usd_to_kes,

            -- How closely this car matches the requested filters (lower = better)
            CASE
                WHEN :year IS NULL                               THEN 0
                WHEN cl.year = :year                            THEN 0
                WHEN cl.year IN (:year_minus, :year_plus)       THEN 1
                ELSE 2
            END AS year_score,
            CASE
                WHEN :engine_size IS NULL                                   THEN 0
                WHEN cl.engine_size_cc = :engine_size                       THEN 0
                WHEN cl.engine_size_cc BETWEEN :engine_min AND :engine_max  THEN 1
                ELSE 2
            END AS engine_score,
            CASE
                WHEN :fuel_type = '%'              THEN 0
                WHEN cl.fuel_type ILIKE :fuel_type THEN 0
                ELSE 1
            END AS fuel_score,
            CASE
                WHEN :transmission = '%'                   THEN 0
                WHEN cl.transmission ILIKE :transmission   THEN 0
                ELSE 1
            END AS trans_score,
            CASE
                WHEN :mileage_max IS NULL          THEN 0
                WHEN cl.mileage_km <= :mileage_max THEN 0
                ELSE 1
            END AS mileage_score

        FROM cleaned_listings cl
        JOIN import_costs ic ON cl.id = ic.cleaned_id
        WHERE {japan_where}
    ),

    -- Best Kenya match for each Japan car
    kenya_matches AS (
        SELECT
            j.id AS japan_id,
            k.model     AS kenya_model,
            k.price_kes AS kenya_price_kes,
            k.year      AS kenya_year,
            k.mileage_km AS kenya_mileage,
            ROW_NUMBER() OVER (
                PARTITION BY j.id
                ORDER BY
                    ABS(j.year - k.year),
                    CASE
                        WHEN j.model ILIKE '%' || k.model || '%'
                          OR k.model ILIKE '%' || j.model || '%' THEN 1
                        ELSE 2
                    END,
                    ABS(COALESCE(j.mileage_km, 0) - COALESCE(k.mileage_km, 0))
            ) AS rank
        FROM japan_cars j
        JOIN cleaned_listings k
            ON  k.make      = j.make
            AND k.is_import = false
            AND k.model ILIKE :model
    ),

    best_kenya AS (SELECT * FROM kenya_matches WHERE rank = 1)

    SELECT
        j.id,
        j.make,
        j.model,
        j.year,
        j.engine_size_cc,
        j.mileage_km,
        j.fuel_type,
        j.transmission,
        j.drive_type,
        j.fob_price_usd,
        j.import_cost_kes,
        j.usd_to_kes,

        k.kenya_model,
        k.kenya_price_kes,
        k.kenya_year,
        k.kenya_mileage,

        -- Verdict
        CASE
            WHEN k.kenya_price_kes IS NULL             THEN 'NO_LOCAL_DATA'
            WHEN j.import_cost_kes < k.kenya_price_kes THEN 'IMPORT_CHEAPER'
            ELSE 'LOCAL_CHEAPER'
        END AS recommendation,

        -- Savings (positive = import saves money, negative = buying local saves money)
        CASE
            WHEN k.kenya_price_kes IS NULL THEN NULL
            ELSE ROUND((k.kenya_price_kes - j.import_cost_kes)::numeric, 0)
        END AS savings_kes,

        -- Match quality score (lower = closer to what was requested)
        (j.year_score + j.engine_score + j.fuel_score + j.trans_score + j.mileage_score)
            AS match_score

    FROM japan_cars j
    LEFT JOIN best_kenya k ON j.id = k.japan_id

    ORDER BY
        match_score ASC,
        savings_kes DESC NULLS LAST

    LIMIT  :limit
    OFFSET :offset
    """

    result = db.execute(text(query), params)
    return [dict(row) for row in result.mappings().all()]


def count_comparisons(
    db: Session,
    make: Optional[str] = None,
    model: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
) -> int:
    """
    Count Japan listings matching the given filters.
    Used by the API to support pagination.
    """
    conditions = ["cl.is_import = true"]
    params: dict = {}

    if make:
        conditions.append("cl.make ILIKE :make")
        params["make"] = f"%{make.strip()}%"
    if model:
        conditions.append("cl.model ILIKE :model")
        params["model"] = f"%{model.strip()}%"
    if year_min:
        conditions.append("cl.year >= :year_min")
        params["year_min"] = year_min
    if year_max:
        conditions.append("cl.year <= :year_max")
        params["year_max"] = year_max

    where = " AND ".join(conditions)
    result = db.execute(
        text(f"""
            SELECT COUNT(*) AS total
            FROM cleaned_listings cl
            JOIN import_costs ic ON cl.id = ic.cleaned_id
            WHERE {where}
        """),
        params,
    )
    row = result.mappings().first()
    return int(row["total"]) if row else 0