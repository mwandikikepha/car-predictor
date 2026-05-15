from sqlalchemy import (Column,Integer,String,Float,DateTime,Text,Boolean,UniqueConstraint,Index,)
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class RawListing(Base):
    __tablename__ = "raw_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(50), nullable=False, index=True)
    source = Column(String(50), nullable=False)  
    scraped_at = Column(DateTime, default=datetime.utcnow)

    # Raw fields
    make = Column(String(100))
    model = Column(String(100))
    year = Column(Integer)
    price = Column(Float)  
    currency = Column(String(10)) 
    mileage = Column(Float)
    mileage_unit = Column(String(10))  
    engine_size = Column(String(50))  
    fuel_type = Column(String(50))
    transmission = Column(String(50))
    body_type = Column(String(50))
    color = Column(String(50))
    drive_type = Column(String(50))  
    location = Column(String(200))  

    # Raw JSON fallback for extra fields
    raw_data = Column(Text)

    __table_args__ = (
        Index("idx_raw_source_url", "source", "make", "model", "year"),
    )


class CleanedListing(Base):
    __tablename__ = "cleaned_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_id = Column(Integer, nullable=True)  # link back to raw
    batch_id = Column(String(50), nullable=False, index=True)

    # Normalized fields
    _id = Column(String(100), unique=True, nullable=False)  
    source = Column(String(50), nullable=False)

    make = Column(String(100), nullable=False, index=True)
    model = Column(String(100), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    price_usd = Column(Float, nullable=False)  
    price_kes = Column(Float)
    price_original = Column(Float)
    original_currency = Column(String(10))
    mileage_km = Column(Float)
    engine_size_cc = Column(Integer)
    fuel_type = Column(String(50))
    transmission = Column(String(50))
    body_type = Column(String(50))
    color = Column(String(50))
    drive_type = Column(String(50))

    # Metadata
    car_age = Column(Integer)  
    price_per_km = Column(Float)
    is_import = Column(Boolean, default=True)  

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("_id", name="uq_cleaned_id"),
        Index("idx_cleaned_make_model_year", "make", "model", "year"),
        Index("idx_cleaned_price", "price_usd"),
        Index("idx_cleaned_source", "source", "is_import"),
    )


class ImportCost(Base):
    __tablename__ = "import_costs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cleaned_id = Column(Integer, nullable=False)
    calculated_at = Column(DateTime, default=datetime.utcnow)

    # Cost breakdown
    fob_price_usd = Column(Float, nullable=False)  
    insurance_usd = Column(Float, default=0)
    freight_usd = Column(Float, default=0)
    cif_usd = Column(Float, nullable=False)  

    # KRA taxes 
    import_duty_kes = Column(Float)
    excise_duty_kes = Column(Float)
    vat_kes = Column(Float)
    idf_kes = Column(Float)  
    rdl_kes = Column(Float)  
    total_taxes_kes = Column(Float)

    # Other costs 
    port_handling_kes = Column(Float)
    clearing_agent_kes = Column(Float)
    registration_kes = Column(Float)
    inspection_kes = Column(Float)
    other_fees_kes = Column(Float)

    # Totals
    total_landed_cost_kes = Column(Float, nullable=False)
    total_landed_cost_usd = Column(Float)

    # Exchange rate used
    usd_to_kes = Column(Float, nullable=False)


class LocalPrice(Base):
    __tablename__ = "local_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cleaned_id = Column(Integer, nullable=False)

    # Kenyan market price for comparison
    price_kes = Column(Float, nullable=False)
    price_usd = Column(Float)
    source = Column(String(50))  
    listed_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)


class ModelPrediction(Base):
    __tablename__ = "model_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cleaned_id = Column(Integer, nullable=False)

    # Features used
    make = Column(String(100))
    model = Column(String(100))
    year = Column(Integer)
    mileage_km = Column(Float)
    engine_size_cc = Column(Integer)
    fuel_type = Column(String(50))
    transmission = Column(String(50))
    body_type = Column(String(50))

    # Prediction
    predicted_price_usd = Column(Float, nullable=False)
    actual_price_usd = Column(Float)
    residual = Column(Float) 

    predicted_at = Column(DateTime, default=datetime.utcnow)
    model_version = Column(String(50)) 