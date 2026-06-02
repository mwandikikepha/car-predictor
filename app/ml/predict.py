# app/ml/predict.py
#
# Loads the trained model and exposes predict_price() for the API router.
# This module is import-safe — if the model file doesn't exist yet it raises
# a clear error rather than crashing silently.

import json
import logging
from pathlib import Path
from functools import lru_cache

import numpy as np
import joblib
import sys

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from app.ml.features import build_inference_features

logger = logging.getLogger(__name__)

ML_DIR     = Path(__file__).parent
MODEL_PATH = ML_DIR / "model.joblib"
META_PATH  = ML_DIR / "model_meta.json"

# KES per USD — keep in sync with settings.py
# (imported here to avoid circular imports with the config module)
USD_TO_KES = 130.0


# ── Model loading (cached — only loads once per process) ──────────

@lru_cache(maxsize=1)
def _load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}. "
            "Run `uv run python app/ml/train.py` first."
        )
    model = joblib.load(MODEL_PATH)
    logger.info(f"ML model loaded from {MODEL_PATH}")
    return model


@lru_cache(maxsize=1)
def _load_meta() -> dict:
    if not META_PATH.exists():
        raise FileNotFoundError(
            f"Model metadata not found at {META_PATH}. "
            "Run `uv run python app/ml/train.py` first."
        )
    with open(META_PATH) as f:
        return json.load(f)


def model_is_ready() -> bool:
    """Safe check used by the API health endpoint."""
    return MODEL_PATH.exists() and META_PATH.exists()


# ── Confidence interval ───────────────────────────────────────────

def _confidence_interval(predicted_usd: float, mape: float) -> tuple[float, float]:
    """
    Derive a ±confidence range from the model's MAPE.
    e.g. MAPE=15% on a $5,000 prediction → [$4,250, $5,750]
    """
    margin = predicted_usd * (mape / 100)
    return predicted_usd - margin, predicted_usd + margin


def _price_verdict(
    predicted_usd: float,
    listing_price_usd: float | None,
    mape: float,
) -> str:
    """
    Human-readable assessment of whether a listed price is fair.
    Only generated when a listing price is provided for comparison.
    """
    if listing_price_usd is None:
        return "Provide a listing price to see if it's fair value."

    diff_pct = ((listing_price_usd - predicted_usd) / predicted_usd) * 100
    margin   = mape  # use model MAPE as the "fair zone"

    if abs(diff_pct) <= margin:
        return f"Fair price — within the expected range for this spec."
    elif diff_pct > margin:
        return (
            f"Listed at {diff_pct:.0f}% above predicted value "
            f"(${listing_price_usd:,.0f} vs predicted ${predicted_usd:,.0f}). "
            f"Consider negotiating."
        )
    else:
        return (
            f"Listed at {abs(diff_pct):.0f}% below predicted value "
            f"(${listing_price_usd:,.0f} vs predicted ${predicted_usd:,.0f}). "
            f"Could be a good deal — verify the listing details."
        )


# ── Main prediction function ──────────────────────────────────────

def predict_price(
    make: str,
    model: str,
    year: int,
    mileage_km: float | None = None,
    engine_size_cc: int | None = None,
    fuel_type: str | None = None,
    transmission: str | None = None,
    source: str = "sbt_japan",
    listing_price_usd: float | None = None,
) -> dict:
    """
    Predict the FOB Japan price for a car with the given specs.

    Args:
        make, model, year       — required
        mileage_km              — optional but strongly improves accuracy
        engine_size_cc          — optional
        fuel_type               — optional (Petrol / Diesel / Hybrid / Electric)
        transmission            — optional (Automatic / Manual / CVT)
        source                  — which Japan platform (affects price slightly)
        listing_price_usd       — if provided, get a fair-price verdict

    Returns a dict ready for the API response.
    """
    xgb_model = _load_model()
    meta       = _load_meta()

    training_columns = meta["training_columns"]
    mape             = meta["metrics"]["mape"]
    car_age          = 2026 - year

    listing = {
        "make":          make,
        "model":         model,
        "year":          year,
        "car_age":       car_age,
        "mileage_km":    mileage_km,
        "engine_size_cc": engine_size_cc,
        "fuel_type":     fuel_type,
        "transmission":  transmission,
        "source":        source,
    }

    # Build feature row aligned to training columns
    X = build_inference_features(listing, training_columns)

    # Predict
    predicted_usd = float(xgb_model.predict(X)[0])
    predicted_usd = max(predicted_usd, 500)   # floor: no car predicted below $500

    predicted_kes = predicted_usd * USD_TO_KES
    low_usd, high_usd = _confidence_interval(predicted_usd, mape)

    return {
        # Core prediction
        "predicted_price_usd":       round(predicted_usd, 2),
        "predicted_price_kes":       f"KSh {round(predicted_kes):,}",
        "price_range_usd": {
            "low":  round(max(low_usd,  500), 2),
            "high": round(high_usd, 2),
        },
        "price_range_kes": {
            "low":  f"KSh {round(max(low_usd,  500) * USD_TO_KES):,}",
            "high": f"KSh {round(high_usd * USD_TO_KES):,}",
        },

        # Confidence info
        "confidence_note": (
            f"±{mape:.0f}% based on model accuracy "
            f"(MAE ${meta['metrics']['mae']:,.0f})"
        ),

        # Fair-price verdict (only when listing_price_usd is given)
        "verdict": _price_verdict(predicted_usd, listing_price_usd, mape),

        # Model metadata shown to the user
        "model_info": {
            "r2":          meta["metrics"]["r2"],
            "trained_on":  meta["n_train"],
            "trained_at":  meta["trained_at"],
        },

        # Echo back the input so the frontend can display it
        "input": {
            "make":          make,
            "model":         model,
            "year":          year,
            "mileage_km":    mileage_km,
            "engine_size_cc": engine_size_cc,
            "fuel_type":     fuel_type,
            "transmission":  transmission,
        },
    }