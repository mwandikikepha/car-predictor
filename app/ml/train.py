# app/ml/train.py
#
# Train the XGBoost price prediction model on Japan listings.
# Run from the project root: uv run python app/ml/train.py
#
# Outputs:
#   app/ml/model.joblib       — trained XGBoost model
#   app/ml/model_meta.json    — column names, metrics, feature importance

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd 
import numpy as np 
import joblib
import xgboost as xgb
from numpyencoder import NumpyEncoder
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sqlalchemy.orm import Session
import warnings
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from database.connection import engine
from app.ml.features import build_training_features

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ML_DIR     = Path(__file__).parent
MODEL_PATH = ML_DIR / "model.joblib"
META_PATH  = ML_DIR / "model_meta.json"


# ── Load data ─────────────────────────────────────────────────────

def load_japan_listings() -> list[dict]:
    """Load all Japan import listings from the database."""
    from sqlalchemy import text
    with Session(engine) as db:
        result = db.execute(text("""
            SELECT
                source, make, model, year, car_age,
                price_usd, mileage_km, engine_size_cc,
                fuel_type, transmission, drive_type
            FROM cleaned_listings
            WHERE is_import = true
              AND price_usd IS NOT NULL
              AND price_usd > 0
              AND year IS NOT NULL
            ORDER BY id
        """))
        rows = result.mappings().all()
    logger.info(f"Loaded {len(rows)} Japan listings from DB")
    return [dict(r) for r in rows]


# ── Train ─────────────────────────────────────────────────────────

def train():
    # 1. Load and featurise
    listings = load_japan_listings()
    if len(listings) < 100:
        raise ValueError(
            f"Only {len(listings)} listings — need at least 100 to train. "
            "Run the scrapers and reload the DB first."
        )

    logger.info("Building feature matrix...")
    X, y = build_training_features(listings)
    logger.info(f"Feature matrix shape: {X.shape}  (rows × features)")
    logger.info(f"Price range: ${y.min():,.0f} – ${y.max():,.0f}  "
                f"| Mean: ${y.mean():,.0f}")

    # 2. Train / test split — stratified by price quantile for even coverage
    price_quantile = pd.qcut(y, q=5, labels=False, duplicates="drop")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.2,
        random_state=42,
        stratify=price_quantile,
    )
    logger.info(f"Train: {len(X_train)} rows | Test: {len(X_test)} rows")

    # 3. XGBoost — tuned for used car price prediction
    model = xgb.XGBRegressor(
        n_estimators       = 500,
        max_depth          = 6,
        learning_rate      = 0.05,
        subsample          = 0.8,
        colsample_bytree   = 0.8,
        min_child_weight   = 5,
        reg_alpha          = 0.1,     # L1 regularisation
        reg_lambda         = 1.0,     # L2 regularisation
        random_state       = 42,
        n_jobs             = -1,
        early_stopping_rounds = 30,
        eval_metric        = "mae",
        verbosity          = 0,
    )

    logger.info("Training XGBoost model...")
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )
    logger.info(f"Best iteration: {model.best_iteration}")

    # 4. Evaluate
    y_pred = model.predict(X_test)

    mae  = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2   = r2_score(y_test, y_pred)
    mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100

    logger.info("=" * 50)
    logger.info("TEST SET METRICS")
    logger.info(f"  R²   : {r2:.4f}  (1.0 = perfect)")
    logger.info(f"  MAE  : ${mae:,.0f}  (mean absolute error)")
    logger.info(f"  RMSE : ${rmse:,.0f}")
    logger.info(f"  MAPE : {mape:.1f}%  (mean absolute % error)")
    logger.info("=" * 50)

    # 5-fold cross-validation on full dataset
    logger.info("Running 5-fold cross-validation...")
    cv_scores = cross_val_score(
        xgb.XGBRegressor(
            n_estimators=model.best_iteration or 200,
            max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, n_jobs=-1, verbosity=0,
        ),
        X, y, cv=5, scoring="r2", n_jobs=-1,
    )
    logger.info(f"  CV R² scores: {[f'{s:.3f}' for s in cv_scores]}")
    logger.info(f"  CV R² mean:   {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    # 5. Feature importance — top 20
    importance = dict(zip(X.columns, model.feature_importances_))
    top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:20]
    logger.info("\nTop 20 features by importance:")
    for feat, imp in top_features:
        bar = "█" * int(imp * 200)
        logger.info(f"  {feat:<35} {imp:.4f}  {bar}")

    # 6. Save model and metadata
    joblib.dump(model, MODEL_PATH)
    logger.info(f"Model saved → {MODEL_PATH}")

    meta = {
        "trained_at":       datetime.now().isoformat(),
        "n_train":          len(X_train),
        "n_test":           len(X_test),
        "n_features":       X.shape[1],
        "training_columns": list(X.columns),
        "metrics": {
            "r2":   round(r2,   4),
            "mae":  round(mae,  2),
            "rmse": round(rmse, 2),
            "mape": round(mape, 2),
            "cv_r2_mean": round(float(cv_scores.mean()), 4),
            "cv_r2_std":  round(float(cv_scores.std()),  4),
        },
        "top_features": [
            {"feature": f, "importance": round(i, 4)}
            for f, i in top_features
        ],
        "price_stats": {
            "min":  round(float(y.min()),  2),
            "max":  round(float(y.max()),  2),
            "mean": round(float(y.mean()), 2),
            "median": round(float(y.median()), 2),
        },
    }

    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2, cls=NumpyEncoder)
    logger.info(f"Metadata saved → {META_PATH}")

    return model, meta


if __name__ == "__main__":
    import pandas as pd  # needed for qcut in train()
    model, meta = train()
    logger.info("\nTraining complete.")
    logger.info(f"R²={meta['metrics']['r2']}  "
                f"MAE=${meta['metrics']['mae']:,.0f}  "
                f"MAPE={meta['metrics']['mape']}%")