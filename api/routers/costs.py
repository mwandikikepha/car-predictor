# api/routers/costs.py
#
# FastAPI router — shapes service results into user-facing responses.
# All query logic lives in app/comparison_service.py.

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from pydantic import BaseModel

from api.dependencies import get_db
from app.comparison_service import get_comparisons, count_comparisons

router = APIRouter(prefix="/costs", tags=["costs"])


# ── Response schemas ──────────────────────────────────────────────

class CarListing(BaseModel):
    id: int
    trim: str
    year: int
    mileage_km: Optional[int] = None
    engine_cc: Optional[int] = None
    fuel: Optional[str] = None
    transmission: Optional[str] = None


class LocalMarket(BaseModel):
    price: str
    year: Optional[int] = None
    note: Optional[str] = None


class CompareResult(BaseModel):
    make: str
    model: str
    car: CarListing
    import_cost: str
    local_market: Optional[LocalMarket] = None
    verdict: str
    difference: Optional[str] = None
    verdict_label: str
    verdict_color: str


class CostBreakdownItem(BaseModel):
    label: str
    amount_kes: float
    amount_kes_formatted: str
    category: str


class CostBreakdownResponse(BaseModel):
    car_id: int
    make: str
    model: str
    trim: str
    year: int
    total_landed_cost: str
    total_landed_cost_kes: float
    usd_to_kes: float
    items: List[CostBreakdownItem]


# ── Formatting helpers ────────────────────────────────────────────

def _fmt(value) -> Optional[str]:
    if value is None:
        return None
    return f"KSh {float(value):,.0f}"


def _f(value) -> Optional[float]:
    return float(value) if value is not None else None


def _clean_model_name(raw: str) -> str:
    return raw.strip().split()[0].title() if raw else raw


def _clean_trim(raw: str) -> str:
    return raw.strip().title() if raw else raw


def _difference_text(savings_kes: Optional[float]) -> Optional[str]:
    if savings_kes is None:
        return None
    if savings_kes > 0:
        return f"KSh {savings_kes:,.0f} cheaper to import"
    if savings_kes < 0:
        return f"KSh {abs(savings_kes):,.0f} cheaper to buy locally"
    return "Same price either way"


def _verdict_meta(recommendation: str):
    if recommendation == "IMPORT_CHEAPER":
        return "Import", "green"
    if recommendation == "LOCAL_CHEAPER":
        return "Buy local", "red"
    return "No data", "gray"


def _local_note(kenya_model: Optional[str], kenya_year: Optional[int],
                japan_year: Optional[int]) -> Optional[str]:
    parts = []
    if kenya_year and japan_year and int(kenya_year) != int(japan_year):
        parts.append(f"{int(kenya_year)} model on local market")
    if kenya_model and "hybrid" in kenya_model.lower():
        parts.append("Hybrid variant")
    return " · ".join(parts) if parts else None


def _shape_row(row: dict) -> CompareResult:
    """Convert a raw service row into a user-facing CompareResult."""
    savings    = _f(row.get("savings_kes"))
    import_kes = _f(row.get("import_cost_kes"))
    kenya_kes  = _f(row.get("kenya_price_kes"))
    recommendation = row.get("recommendation", "NO_LOCAL_DATA")
    verdict_label, verdict_color = _verdict_meta(recommendation)

    local = None
    if kenya_kes is not None:
        local = LocalMarket(
            price=_fmt(kenya_kes),
            year=int(row["kenya_year"]) if row.get("kenya_year") else None,
            note=_local_note(row.get("kenya_model"), row.get("kenya_year"),
                             row.get("year")),
        )

    return CompareResult(
        make=row["make"],
        model=_clean_model_name(row["model"]),
        car=CarListing(
            id=row["id"],
            trim=_clean_trim(row["model"]),
            year=row["year"],
            mileage_km=int(row["mileage_km"]) if row.get("mileage_km") else None,
            engine_cc=int(row["engine_size_cc"]) if row.get("engine_size_cc") else None,
            fuel=row.get("fuel_type"),
            transmission=row.get("transmission"),
        ),
        import_cost=_fmt(import_kes),
        local_market=local,
        verdict=recommendation,
        difference=_difference_text(savings),
        verdict_label=verdict_label,
        verdict_color=verdict_color,
    )


# ── Routes ────────────────────────────────────────────────────────

@router.get("/compare", response_model=List[CompareResult])
def compare_prices(
    make: Optional[str] = Query(None, description="e.g. Toyota, Subaru, Nissan"),
    model: Optional[str] = Query(None, description="e.g. Vitz, Forester, X-Trail"),
    year: Optional[int] = Query(None, description="Exact year e.g. 2019"),
    year_min: Optional[int] = Query(None, description="Year range lower bound"),
    year_max: Optional[int] = Query(None, description="Year range upper bound"),
    engine_size_cc: Optional[int] = Query(None, description="Engine cc e.g. 1500"),
    fuel_type: Optional[str] = Query(None, description="Petrol, Diesel, Hybrid, Electric"),
    mileage_km_max: Optional[int] = Query(None, description="Max Japan mileage in km"),
    transmission: Optional[str] = Query(None, description="Automatic, Manual, CVT"),
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Compare Japan import costs vs Kenyan local prices."""
    if not make and not model:
        raise HTTPException(status_code=422,
                            detail="Provide at least one of: make, model")

    rows = get_comparisons(
        db,
        make=make, model=model, year=year,
        year_min=year_min, year_max=year_max,
        engine_size_cc=engine_size_cc, fuel_type=fuel_type,
        mileage_km_max=mileage_km_max, transmission=transmission,
        limit=limit, offset=offset,
    )
    return [_shape_row(r) for r in rows]


@router.get("/compare/count")
def compare_count(
    make: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    year_min: Optional[int] = Query(None),
    year_max: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Total matching Japan listings — use for frontend pagination."""
    if not make and not model:
        raise HTTPException(status_code=422,
                            detail="Provide at least one of: make, model")
    total = count_comparisons(db, make=make, model=model,
                              year_min=year_min, year_max=year_max)
    return {"total": total}


@router.get("/{car_id}/breakdown", response_model=CostBreakdownResponse)
def cost_breakdown(car_id: int, db: Session = Depends(get_db)):
    """Full KRA cost breakdown as ordered line items for a receipt-style UI."""
    result = db.execute(text("""
        SELECT
            cl.id, cl.make, cl.model, cl.year,
            ic.fob_price_usd, ic.freight_usd, ic.insurance_usd, ic.cif_usd,
            ic.import_duty_kes, ic.excise_duty_kes, ic.vat_kes,
            ic.idf_kes, ic.rdl_kes,
            ic.port_handling_kes, ic.clearing_agent_kes,
            ic.registration_kes, ic.inspection_kes, ic.other_fees_kes,
            ic.total_landed_cost_kes, ic.usd_to_kes
        FROM import_costs ic
        JOIN cleaned_listings cl ON cl.id = ic.cleaned_id
        WHERE ic.cleaned_id = :car_id
    """), {"car_id": car_id})

    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404,
                            detail=f"No cost data for car id={car_id}. "
                                   "Run cost_engine.py first.")

    d = dict(row)
    r = float(d["usd_to_kes"])

    def u(usd_val) -> float:
        return round(float(usd_val) * r, 0) if usd_val else 0.0

    def k(kes_val) -> float:
        return round(float(kes_val), 0) if kes_val else 0.0

    items = [
        CostBreakdownItem(label="Purchase price (FOB Japan)",
                          amount_kes=u(d["fob_price_usd"]),
                          amount_kes_formatted=_fmt(u(d["fob_price_usd"])),
                          category="purchase"),
        CostBreakdownItem(label="Freight to Mombasa",
                          amount_kes=u(d["freight_usd"]),
                          amount_kes_formatted=_fmt(u(d["freight_usd"])),
                          category="shipping"),
        CostBreakdownItem(label="Marine insurance",
                          amount_kes=u(d["insurance_usd"]),
                          amount_kes_formatted=_fmt(u(d["insurance_usd"])),
                          category="shipping"),
        CostBreakdownItem(label="Import duty (25% of CIF)",
                          amount_kes=k(d["import_duty_kes"]),
                          amount_kes_formatted=_fmt(k(d["import_duty_kes"])),
                          category="taxes"),
        CostBreakdownItem(label="Excise duty (20%)",
                          amount_kes=k(d["excise_duty_kes"]),
                          amount_kes_formatted=_fmt(k(d["excise_duty_kes"])),
                          category="taxes"),
        CostBreakdownItem(label="VAT (16%)",
                          amount_kes=k(d["vat_kes"]),
                          amount_kes_formatted=_fmt(k(d["vat_kes"])),
                          category="taxes"),
        CostBreakdownItem(label="Import declaration fee (3.5%)",
                          amount_kes=k(d["idf_kes"]),
                          amount_kes_formatted=_fmt(k(d["idf_kes"])),
                          category="taxes"),
        CostBreakdownItem(label="Railway development levy (2%)",
                          amount_kes=k(d["rdl_kes"]),
                          amount_kes_formatted=_fmt(k(d["rdl_kes"])),
                          category="taxes"),
        CostBreakdownItem(label="Port handling",
                          amount_kes=k(d["port_handling_kes"]),
                          amount_kes_formatted=_fmt(k(d["port_handling_kes"])),
                          category="local_charges"),
        CostBreakdownItem(label="Clearing agent fees",
                          amount_kes=k(d["clearing_agent_kes"]),
                          amount_kes_formatted=_fmt(k(d["clearing_agent_kes"])),
                          category="local_charges"),
        CostBreakdownItem(label="Vehicle registration",
                          amount_kes=k(d["registration_kes"]),
                          amount_kes_formatted=_fmt(k(d["registration_kes"])),
                          category="local_charges"),
        CostBreakdownItem(label="Pre-shipment inspection",
                          amount_kes=k(d["inspection_kes"]),
                          amount_kes_formatted=_fmt(k(d["inspection_kes"])),
                          category="local_charges"),
        CostBreakdownItem(label="Other fees",
                          amount_kes=k(d["other_fees_kes"]),
                          amount_kes_formatted=_fmt(k(d["other_fees_kes"])),
                          category="local_charges"),
    ]

    total = k(d["total_landed_cost_kes"])
    return CostBreakdownResponse(
        car_id=d["id"],
        make=d["make"],
        model=_clean_model_name(d["model"]),
        trim=_clean_trim(d["model"]),
        year=d["year"],
        total_landed_cost=_fmt(total),
        total_landed_cost_kes=total,
        usd_to_kes=r,
        items=items,
    )