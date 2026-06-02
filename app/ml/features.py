# app/ml/features.py
#
# Single source of truth for feature engineering.
# train.py and predict.py both call this — features are always identical
# between training and inference.

import re
import json
import numpy as np
import pandas as pd
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────

MIN_MAKE_FREQUENCY  = 20   # makes below this threshold → "Other"
MIN_MODEL_FREQUENCY = 10   # models below this threshold → "Other"

FUEL_CATEGORIES  = ["Petrol", "Diesel", "Hybrid", "Electric",
                    "Plug-in Hybrid", "LPG", "CNG", "Unknown"]
TRANS_CATEGORIES = ["Automatic", "Manual", "CVT", "Semi-Automatic", "Unknown"]
SOURCE_CATEGORIES = ["sbt_japan", "beforward_japan",
                     "carfromjapan", "jct_japan", "Unknown"]

MILEAGE_BINS   = [0, 30_000, 60_000, 100_000, 150_000, 200_000, float("inf")]
MILEAGE_LABELS = ["0-30k", "30-60k", "60-100k", "100-150k", "150-200k", "200k-plus"]

NUMERICAL_FEATURES = [
    "year", "mileage_km", "engine_size_cc", "car_age",
    "mileage_per_year", "mileage_intensity",
]

ML_DIR        = Path(__file__).parent
ENCODERS_PATH = ML_DIR / "encoders.json"


# ── Encoder persistence ───────────────────────────────────────────

def save_encoders(make_map: dict, model_map: dict) -> None:
    with open(ENCODERS_PATH, "w") as f:
        json.dump({"make_map": make_map, "model_map": model_map}, f, indent=2)


def load_encoders() -> tuple[dict, dict]:
    if not ENCODERS_PATH.exists():
        raise FileNotFoundError(
            f"Encoders not found at {ENCODERS_PATH}. Run train.py first."
        )
    with open(ENCODERS_PATH) as f:
        data = json.load(f)
    return data["make_map"], data["model_map"]


# ── Cleaning helpers ──────────────────────────────────────────────

def _clean_model(model: str | None) -> str:
    if not model:
        return "Unknown"
    words = re.sub(r"[^\w\s]", "", str(model).strip()).split()
    return " ".join(words[:2]).title() if words else "Unknown"


def _clean_make(make: str | None) -> str:
    return str(make).strip().title() if make else "Unknown"


def _safe_float(value, default: float = np.nan) -> float:
    try:
        v = float(value)
        return v if np.isfinite(v) else default
    except (TypeError, ValueError):
        return default


# ── Shared derived-feature helpers ───────────────────────────────

def _add_derived_numericals(df: pd.DataFrame) -> pd.DataFrame:
    """Add mileage_per_year, mileage_intensity, mileage_bucket to df in-place."""
    df["mileage_per_year"] = np.where(
        (df["car_age"] > 0) & df["mileage_km"].notna(),
        df["mileage_km"] / df["car_age"],
        np.nan,
    )
    df["mileage_intensity"] = df["mileage_km"] / df["car_age"].clip(lower=1)

    df["mileage_bucket"] = pd.cut(
        df["mileage_km"].fillna(50_000),
        bins=MILEAGE_BINS,
        labels=MILEAGE_LABELS,
    ).astype(str)

    return df


# ── Build all column blocks as separate DataFrames, then concat ───
# This avoids the PerformanceWarning caused by repeated frame.insert calls.

def _encode(
    df: pd.DataFrame,
    make_values: list[str],
    model_values: list[str],
) -> pd.DataFrame:
    """
    Build the full feature matrix from a prepared df.
    All column blocks are constructed independently then joined once
    with pd.concat — no per-column inserts, no fragmentation warning.
    """
    blocks: list[pd.DataFrame] = []

    # ── Numerical block ───────────────────────────────────────────
    num_data = {}
    for col in NUMERICAL_FEATURES:
        num_data[col] = df[col] if col in df.columns else pd.Series(
            np.nan, index=df.index
        )
    blocks.append(pd.DataFrame(num_data, index=df.index))

    # ── Make one-hot block ────────────────────────────────────────
    make_data = {
        f"make_{v}": (df["make_encoded"] == v).astype(np.int8)
        for v in sorted(make_values)
    }
    blocks.append(pd.DataFrame(make_data, index=df.index))

    # ── Model one-hot block ───────────────────────────────────────
    model_data = {
        f"model_{v}": (df["model_encoded"] == v).astype(np.int8)
        for v in sorted(model_values)
    }
    blocks.append(pd.DataFrame(model_data, index=df.index))

    # ── Mileage bucket one-hot block ──────────────────────────────
    bucket_data = {
        f"mileage_bucket_{lab}": (df["mileage_bucket"] == lab).astype(np.int8)
        for lab in MILEAGE_LABELS
    }
    blocks.append(pd.DataFrame(bucket_data, index=df.index))

    # ── Fuel one-hot block ────────────────────────────────────────
    fuel_data = {
        f"fuel_{v}": (df["fuel_clean"] == v).astype(np.int8)
        for v in FUEL_CATEGORIES
    }
    blocks.append(pd.DataFrame(fuel_data, index=df.index))

    # ── Transmission one-hot block ────────────────────────────────
    trans_data = {
        f"trans_{v}": (df["trans_clean"] == v).astype(np.int8)
        for v in TRANS_CATEGORIES
    }
    blocks.append(pd.DataFrame(trans_data, index=df.index))

    # ── Source one-hot block ──────────────────────────────────────
    source_data = {
        f"source_{v}": (df["source_clean"] == v).astype(np.int8)
        for v in SOURCE_CATEGORIES
    }
    blocks.append(pd.DataFrame(source_data, index=df.index))

    return pd.concat(blocks, axis=1)


# ── Training feature builder ──────────────────────────────────────

def build_training_features(
    listings: list[dict],
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Convert raw Japan listing dicts → (X, y).
    Saves encoders.json for use by predict.py.
    """
    df = pd.DataFrame(listings)

    # Target
    df["price_usd"] = df["price_usd"].apply(_safe_float)
    df = df.dropna(subset=["price_usd"])
    df = df[df["price_usd"] > 0]

    # Remove top/bottom 1% outliers
    p1, p99 = df["price_usd"].quantile(0.01), df["price_usd"].quantile(0.99)
    df = df[(df["price_usd"] >= p1) & (df["price_usd"] <= p99)]
    df = df.reset_index(drop=True)

    y = df["price_usd"].copy()

    # Numericals
    for col in ["year", "mileage_km", "engine_size_cc", "car_age"]:
        df[col] = df[col].apply(_safe_float)

    df = _add_derived_numericals(df)

    # Make encoding
    df["make_clean"] = df["make"].apply(_clean_make)
    make_counts      = df["make_clean"].value_counts()
    frequent_makes   = set(make_counts[make_counts >= MIN_MAKE_FREQUENCY].index)
    make_map         = {m: m for m in frequent_makes}
    df["make_encoded"] = df["make_clean"].apply(
        lambda m: m if m in frequent_makes else "Other"
    )

    # Model encoding
    df["model_clean"]   = df["model"].apply(_clean_model)
    model_counts        = df["model_clean"].value_counts()
    frequent_models     = set(model_counts[model_counts >= MIN_MODEL_FREQUENCY].index)
    model_map           = {m: m for m in frequent_models}
    df["model_encoded"] = df["model_clean"].apply(
        lambda m: m if m in frequent_models else "Other"
    )

    # Save for inference
    save_encoders(make_map, model_map)

    # Categorical cleaning
    df["fuel_clean"]   = df["fuel_type"].fillna("Unknown").apply(
        lambda v: v if v in FUEL_CATEGORIES else "Unknown"
    )
    df["trans_clean"]  = df["transmission"].fillna("Unknown").apply(
        lambda v: v if v in TRANS_CATEGORIES else "Unknown"
    )
    df["source_clean"] = df["source"].fillna("Unknown").apply(
        lambda v: v if v in SOURCE_CATEGORIES else "Unknown"
    )

    make_values  = sorted(df["make_encoded"].unique())
    model_values = sorted(df["model_encoded"].unique())

    X = _encode(df, make_values, model_values)
    return X.reset_index(drop=True), y.reset_index(drop=True)


# ── Inference feature builder ─────────────────────────────────────

def build_inference_features(
    listing: dict,
    training_columns: list[str],
) -> pd.DataFrame:
    """
    Build a single-row feature DataFrame aligned to training_columns.
    Missing columns are filled with 0 (not NaN) so XGBoost never sees
    unexpected nulls at inference time.
    """
    make_map, model_map = load_encoders()

    year           = _safe_float(listing.get("year"))
    mileage_km     = _safe_float(listing.get("mileage_km"))
    engine_size_cc = _safe_float(listing.get("engine_size_cc"))
    car_age        = (2026 - year) if np.isfinite(year) else np.nan

    mileage_per_year = (
        mileage_km / car_age
        if np.isfinite(mileage_km) and car_age and car_age > 0
        else np.nan
    )
    mileage_intensity = (
        mileage_km / max(car_age, 1)
        if np.isfinite(mileage_km) and np.isfinite(car_age)
        else np.nan
    )

    # Mileage bucket for this single row
    km = mileage_km if np.isfinite(mileage_km) else 50_000
    bucket_series = pd.cut(
        pd.Series([km]),
        bins=MILEAGE_BINS,
        labels=MILEAGE_LABELS,
    ).astype(str)
    mileage_bucket = bucket_series.iloc[0]

    make   = _clean_make(listing.get("make"))
    make_enc = make if make in make_map else "Other"

    model  = _clean_model(listing.get("model"))
    model_enc = model if model in model_map else "Other"

    fuel   = listing.get("fuel_type") or "Unknown"
    fuel   = fuel if fuel in FUEL_CATEGORIES else "Unknown"

    trans  = listing.get("transmission") or "Unknown"
    trans  = trans if trans in TRANS_CATEGORIES else "Unknown"

    source = listing.get("source") or "Unknown"
    source = source if source in SOURCE_CATEGORIES else "Unknown"

    # Build row as dict — start with zeros for all training columns
    row: dict = {col: 0 for col in training_columns}

    # Fill numericals
    row["year"]              = year
    row["mileage_km"]        = mileage_km
    row["engine_size_cc"]    = engine_size_cc
    row["car_age"]           = car_age
    row["mileage_per_year"]  = mileage_per_year
    row["mileage_intensity"] = mileage_intensity

    # One-hot flags — set to 1 only if the column exists in training set
    for col_name, value in [
        (f"make_{make_enc}",              1),
        (f"model_{model_enc}",            1),
        (f"mileage_bucket_{mileage_bucket}", 1),
        (f"fuel_{fuel}",                  1),
        (f"trans_{trans}",                1),
        (f"source_{source}",              1),
    ]:
        if col_name in row:
            row[col_name] = value

    return pd.DataFrame([row])[training_columns]