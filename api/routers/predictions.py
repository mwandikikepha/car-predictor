# api/routers/predictions.py

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

router = APIRouter(prefix="/predictions", tags=["predictions"])


def _get_predictor():
    """
    Lazy import so the API starts even if the model hasn't been trained yet.
    Raises a clean 503 instead of crashing the server.
    """
    try:
        from app.ml.predict import predict_price, model_is_ready
        if not model_is_ready():
            raise FileNotFoundError()
        return predict_price
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=(
                "ML model not trained yet. "
                "Run `uv run python app/ml/train.py` to train it."
            ),
        )


@router.get("/price")
def predict_price_endpoint(
    make: str = Query(..., description="Car make e.g. Toyota"),
    model: str = Query(..., description="Car model e.g. Vitz"),
    year: int = Query(..., description="Year of manufacture e.g. 2019"),
    mileage_km: Optional[float] = Query(
        None, description="Mileage in km e.g. 50000"
    ),
    engine_size_cc: Optional[int] = Query(
        None, description="Engine size in cc e.g. 1500"
    ),
    fuel_type: Optional[str] = Query(
        None, description="Petrol · Diesel · Hybrid · Electric"
    ),
    transmission: Optional[str] = Query(
        None, description="Automatic · Manual · CVT"
    ),
    listing_price_usd: Optional[float] = Query(
        None,
        description=(
            "The listed FOB price in USD. "
            "Provide this to get a fair-price verdict "
            "(e.g. overpriced / fair / good deal)."
        ),
    ),
):
    """
    Predict the fair FOB Japan price for a car with the given specs.

    Returns:
    - Predicted price in USD and KES
    - Confidence range (±model MAPE)
    - Fair-price verdict if listing_price_usd is provided
    - Model accuracy metrics

    Example:
        GET /api/predictions/price?make=Toyota&model=Vitz&year=2019
            &mileage_km=50000&fuel_type=Petrol&transmission=Automatic
    """
    if year < 1990 or year > 2026:
        raise HTTPException(
            status_code=422,
            detail=f"Year {year} is outside the supported range (1990–2026)."
        )

    predict_price = _get_predictor()

    try:
        result = predict_price(
            make               = make,
            model              = model,
            year               = year,
            mileage_km         = mileage_km,
            engine_size_cc     = engine_size_cc,
            fuel_type          = fuel_type,
            transmission       = transmission,
            listing_price_usd  = listing_price_usd,
        )
        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed: {str(e)}"
        )


@router.get("/model-info")
def model_info():
    """
    Returns model training metadata — accuracy metrics, training date,
    number of training samples, top features.
    Use this to display model transparency info in the dashboard.
    """
    try:
        from app.ml.predict import _load_meta, model_is_ready
        if not model_is_ready():
            return {
                "status": "not_trained",
                "message": "Run `uv run python app/ml/train.py` to train the model."
            }
        meta = _load_meta()
        return {
            "status":        "ready",
            "trained_at":    meta["trained_at"],
            "trained_on":    meta["n_train"],
            "n_features":    meta["n_features"],
            "metrics": {
                "r2":        meta["metrics"]["r2"],
                "mae_usd":   meta["metrics"]["mae"],
                "rmse_usd":  meta["metrics"]["rmse"],
                "mape_pct":  meta["metrics"]["mape"],
                "cv_r2_mean": meta["metrics"]["cv_r2_mean"],
                "cv_r2_std":  meta["metrics"]["cv_r2_std"],
            },
            "top_features":  meta["top_features"][:10],
            "price_stats":   meta["price_stats"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))