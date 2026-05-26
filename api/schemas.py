# api/schemas.py

from pydantic import BaseModel
from typing import Optional, List


class CarBase(BaseModel):
    make: str
    model: str
    year: int
    price_usd: float
    price_kes: Optional[float] = None
    mileage_km: Optional[float] = None
    engine_size_cc: Optional[int] = None
    fuel_type: Optional[str] = None
    transmission: Optional[str] = None
    drive_type: Optional[str] = None
    is_import: bool


class CarResponse(CarBase):
    id: int
    _id: str
    source: str
    
    class Config:
        from_attributes = True


class CostBreakdown(BaseModel):
    fob_price_usd: float
    freight_usd: float
    insurance_usd: float
    cif_usd: float
    import_duty_kes: float
    excise_duty_kes: float
    vat_kes: float
    idf_kes: float
    rdl_kes: float
    total_taxes_kes: float
    total_landed_cost_kes: float
    usd_to_kes: float


class ComparisonResult(BaseModel):
    id: int
    make: str
    japan_model: str
    year: int
    engine_size_cc: Optional[int]
    japan_mileage: Optional[float]
    fuel_type: Optional[str]
    transmission: Optional[str]
    drive_type: Optional[str]
    import_cost_kes: float
    kenya_model: Optional[str]
    kenya_price_kes: Optional[float]
    kenya_mileage: Optional[float]
    recommendation: str
    savings_kes: Optional[float]


class DealSummary(BaseModel):
    make: str
    model: str
    year: int
    import_cost: float
    local_price: float
    savings_kes: float
    savings_pct: float


class SearchQuery(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine_size_cc: Optional[int] = None
    fuel_type: Optional[str] = None
    mileage_km_max: Optional[int] = None
    transmission: Optional[str] = None
    limit: int = 30