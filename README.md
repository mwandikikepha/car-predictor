# Japan Car Import Advisory Platform

> An end-to-end ML engineering project — from raw web data to a production prediction API — solving a real financial decision for Kenyan car buyers.

![Python](https://img.shields.io/badge/Python-3.12-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue) ![XGBoost](https://img.shields.io/badge/XGBoost-2.0-orange) ![Playwright](https://img.shields.io/badge/Playwright-1.40-purple) ![scikit--learn](https://img.shields.io/badge/scikit--learn-1.4-orange)

---

## The real-world problem this solves

Every year, thousands of Kenyans import used cars from Japan. The decision  **import from Japan or buy locally** involves a chain of costs most buyers get wrong:

- FOB price at Japanese auction
- Freight to Mombasa port
- KRA import duty (25% of CIF)
- KRA excise duty (20% cascaded on top of duty)
- VAT (16% cascaded further)
- Import Declaration Fee (3.5%)
- Railway Development Levy (2%)
- Port handling, clearing agent, registration

Miscalculate any one of these and a car that looked like a saving becomes a loss. Local dealers know this  and price accordingly.

This platform automates the entire calculation, compares it against live local market data, and uses machine learning to evaluate whether any given Japan listing is **fairly priced, overpriced, or a deal** — even when no local comparison exists.

---

## ML engineering overview

This is a full ML engineering project spanning the entire lifecycle: data acquisition → feature engineering → model training → evaluation → serving → production API.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ML ENGINEERING PIPELINE                         │
│                                                                     │
│  1. DATA ACQUISITION          2. FEATURE ENGINEERING               │
│  ┌─────────────────┐          ┌──────────────────────┐             │
│  │ 4 web scrapers  │          │ Numerical:           │             │
│  │ ~9,700 raw rows │─────────►│  year, mileage,      │             │
│  │ Playwright +    │  clean + │  engine_cc, car_age, │             │
│  │ HTTPX +         │  dedupe  │  mileage_intensity,  │             │
│  │ BeautifulSoup   │          │  mileage_per_year    │             │
│  └─────────────────┘          │                      │             │
│                               │ Categorical (OHE):   │             │
│  3. DOMAIN FEATURE            │  make, model,        │             │
│  ┌─────────────────┐          │  fuel, transmission, │             │
│  │ KRA tax engine  │          │  source, mileage     │             │
│  │ CIF → duty →    │          │  bucket              │             │
│  │ excise → VAT →  │          └──────────────────────┘             │
│  │ landed cost     │                    │                           │
│  └─────────────────┘                   ▼                           │
│          │                  4. MODEL TRAINING                       │
│          │                  ┌──────────────────────┐               │
│          │                  │ XGBoost Regressor    │               │
│          │                  │ 500 estimators       │               │
│          │                  │ Early stopping       │               │
│          │                  │ 80/20 stratified     │               │
│          │                  │ split                │               │
│          │                  │ 5-fold CV            │               │
│          │                  └──────────────────────┘               │
│          │                            │                             │
│          │                  5. EVALUATION & SERVING                 │
│          │                  ┌──────────────────────┐               │
│          └─────────────────►│ R²=0.856  MAPE=17.3% │               │
│                             │ FastAPI prediction   │               │
│                             │ endpoint + fair-     │               │
│                             │ price verdict        │               │
│                             └──────────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Model performance

XGBoost regression trained to predict FOB Japan price (USD) from car specifications.

### Metrics

| Metric | Value | Interpretation |
|---|---|---|
| **R²** | **0.856** | Model explains 85.6% of price variance across all makes |
| **MAE** | **$2,404** | Average prediction error on held-out test set |
| **RMSE** | $3,592 | Penalises large errors — acceptable for high-variance luxury segment |
| **MAPE** | **17.3%** | Used as confidence interval width in the API response |
| **CV R²** | **0.773 ± 0.059** | 5-fold cross-validation — model generalises well |
| Training samples | 2,294 | Japan listings, 80/20 stratified split |
| Test samples | 574 | Held out, never seen during training |

### Feature importance — top 20

```
engine_size_cc          ████████████████  0.083   Most important — drives price more than any other spec
car_age                 █████████         0.048   Age matters more than year alone
year                    █████████         0.046   Correlated with car_age but adds signal
mileage_km              ███████           0.038   Stronger after adding mileage_intensity
make_Mazda              ██████            0.031   Brand premium is real and learned
model_Navara            ██████            0.030   High-value model correctly identified
make_Audi               █████             0.030   European premium correctly learned
model_N Box             █████             0.027   Popular kei car, distinct price band
model_Land Cruiser      █████             0.027   High-value outlier correctly separated
make_Nissan             █████             0.024
model_Vellfire Hybrid   ████              0.023   Luxury MPV premium captured
make_Lexus              ████              0.021
fuel_Diesel             ███               0.018   Diesel commands premium — correct
source_beforward_japan  ███               0.023   Platform-level pricing differences learned
mileage_bucket_200k+    ███               0.019   Commercial van high-mileage penalty
mileage_intensity       ███               0.017   km/year signal for commercial vs private
```

**What this tells us about the model:**  
The top features are exactly what a domain expert would expect — engine size, age, and mileage are universal car price drivers. The model has also learned brand premiums (Mazda, Audi, Lexus), model-level outliers (Land Cruiser, Vellfire), fuel type premiums (diesel), and platform-level pricing differences (BE FORWARD vs SBT price the same car differently). This is not a black box — it has learned real market structure.

### Prediction samples — real-world validation

```
Car                            Year  Predicted   Listed    Diff     Verdict
─────────────────────────────────────────────────────────────────────────────
Toyota Vitz F                  2019  $  7,557  $  4,500  +$3,057   ↓ DEAL
Toyota Probox Van              2019  $  6,819  $  5,000  +$1,819   ↓ DEAL
Mazda Demio                    2019  $  5,967  $  4,800  +$1,167   ↓ DEAL
Nissan Note                    2020  $  7,905  $  5,500  +$2,405   ↓ DEAL
Honda Fit Hybrid               2019  $  9,847  $  6,500  +$3,347   ↓ DEAL
Toyota Corolla Fielder         2020  $ 11,289  $  9,000  +$2,289   ↓ DEAL
Toyota Sienta                  2019  $  9,833  $  8,500  +$1,333   ✓ FAIR
Subaru Forester                2020  $ 12,877  $ 11,000  +$1,877   ✓ FAIR
Nissan Serena                  2020  $ 11,829  $ 12,000    -$171   ✓ FAIR
Toyota Prius                   2019  $ 11,844  $ 11,000    +$844   ✓ FAIR
Toyota Hilux                   2020  $ 17,116  $ 20,000  -$2,884   ✓ FAIR
Toyota Land Cruiser            2019  $ 29,166  $ 28,000  +$1,166   ✓ FAIR  ← 4% off
Toyota Harrier                 2021  $ 17,590  $ 18,000    -$410   ✓ FAIR  ← 2% off
Toyota Vellfire                2020  $ 22,129  $ 22,000    +$129   ✓ FAIR  ← 1% off
Toyota Alphard                 2020  $ 24,547  $ 23,000  +$1,547   ✓ FAIR
BMW 3 Series                   2020  $ 16,842  $ 18,000  -$1,158   ✓ FAIR
Audi A4                        2020  $ 16,664  $ 17,000    -$336   ✓ FAIR  ← 2% off
Mercedes-Benz C Class          2020  $ 18,212  $ 20,000  -$1,788   ✓ FAIR
Lexus NX                       2021  $ 26,714  $ 32,000  -$5,286   ↑ OVER
Land Rover Range Rover         2020  $ 32,421  $ 45,000 -$12,579   ↑ OVER
Toyota Hiace Van (250k km)     2018  $ 14,323  $  7,000  +$7,323   ↓ DEAL
```

**Notable:** Land Cruiser at 4% error, Harrier at 2%, Vellfire at 1%, Audi A4 at 2%. These are the most common import targets in Kenya and the model is essentially exact on all of them.

---

## Feature engineering — design decisions

### Why mileage_intensity instead of just mileage_km

Raw mileage is misleading without context. A 2018 car with 200,000 km is very different from a 2022 car with 200,000 km — the former is normal usage, the latter is a high-stress commercial vehicle. `mileage_intensity = mileage_km / car_age` captures this and proved to be a top-20 feature.

### Why mileage buckets alongside continuous mileage

XGBoost handles continuous features well, but the relationship between mileage and price is non-linear — it drops sharply above 150,000 km (commercial use threshold) and again above 200,000 km. Explicit buckets `<30k · 30-60k · 60-100k · 100-150k · 150-200k · 200k+` let the model learn these threshold effects directly. The `200k+` bucket is particularly important for Toyota HiAce and Probox commercial vehicles that are common imports.

### Why frequency-based make/model grouping

With 18 makes and 100+ models, naive one-hot encoding would produce columns for "Daihatsu Cast" (3 listings) that the model memorises rather than generalises. Makes with fewer than 20 listings and models with fewer than 10 listings are grouped as "Other" — reducing noise and improving CV generalisation.

### Why source platform is a feature

The same Toyota Vitz 2019 is priced differently on SBT Japan vs BE FORWARD. This is a real market phenomenon — different platforms serve different dealer tiers and price accordingly. Including `source` as a feature captures this platform-level price variation. It appeared in the top 15 features.

### Training / inference consistency

A common production ML bug is feature drift between training and inference — the model trains on features computed one way and predicts on features computed differently. This project solves it with a single `features.py` module that both `train.py` and `predict.py` import. `encoders.json` persists the make/model frequency maps from training so inference uses identical grouping. `training_columns` are saved in `model_meta.json` so the inference row is aligned column-by-column to what XGBoost expects.

---

## The comparison engine — ML in production context

The ML model doesn't exist in isolation. It works alongside a real-data comparison engine that pulls live Japan and Kenya listings from the database. Together they cover two complementary scenarios:

**Scenario A — Local data exists (comparison engine)**  
User searches Toyota Harrier 2021. Platform finds 8 Japan listings, calculates full landed cost for each, matches against best Kenya local listing, returns side-by-side comparison with savings amount.

```json
{
  "import_cost": "KSh 5,002,550",
  "local_market": { "price": "KSh 6,350,000" },
  "verdict": "IMPORT_CHEAPER",
  "difference": "KSh 1,347,450 cheaper to import"
}
```

**Scenario B — No local data (ML model)**  
User searches Lexus NX 2021. Platform has no Kenya listings for this model. ML model predicts fair FOB price, generates confidence interval, gives verdict on whether the Japan listing is fairly priced.

```json
{
  "predicted_price_usd": 26714,
  "price_range_usd": { "low": 22171, "high": 31257 },
  "verdict": "Listed at 20% above predicted value. Consider negotiating."
}
```

The ML model also adds value in Scenario A — a user can check whether a specific Japan listing is priced fairly *before* it has been matched against local data, using only the car specs.

---

## KRA tax engine

The cost engine implements Kenya Revenue Authority import tax law in the correct cascaded order. Taxes stack on top of each other — a mistake in the cascade order produces significantly wrong totals.

```python
# Correct cascade (each step builds on the previous)
cif            = fob + freight + insurance
import_duty    = cif * 0.25
excise_base    = cif + import_duty
excise_duty    = excise_base * 0.20
vat_base       = excise_base + excise_duty
vat            = vat_base * 0.16
idf            = cif * 0.035
rdl            = cif * 0.02
total_taxes    = import_duty + excise_duty + vat + idf + rdl
landed_cost    = cif + total_taxes + local_charges
```

Every Japan listing gets this calculation applied once. The resulting `import_costs` table stores every line item individually so the API can return a receipt-style breakdown for any listing.

---

## Data pipeline

### Sources

| Source | Country | Method | Raw rows | After cleaning |
|---|---|---|---|---|
| SBT Japan | Japan | HTTPX + BeautifulSoup | ~6,200 | ~1,591 |
| BE FORWARD | Japan | HTTPX + BeautifulSoup | ~2,619 | ~1,601 |
| Jiji Kenya | Kenya | Playwright (headless Chrome) | ~967 | ~495 |
| Cheki Kenya | Kenya | Playwright (headless Chrome) | ~1,600 | ~1000 |
| **Total** | | | **~11,400** | **~4,687** |



### Deduplication

Each listing gets an MD5 hash of `source + make + model + year + price + mileage`. Including price and mileage prevents two different Japan listings for the same model/year from colliding — a bug in the original implementation that was caught and fixed.

---

## Architecture

```
japan-car-import/
├── app/
│   ├── scrapers/
│   │   ├── base.py                 
│   │   ├── japan_sbt.py             
│   │   ├── japan_beforward.py       
│   │   ├── kenya_jiji.py            
│   │   ├── kenya_cheki.py           
│   │   └── run_scrapers.py          
│   ├── ml/
│   │   ├── features.py            
│   │   ├── train.py                
│   │   ├── predict.py               
│   │   ├── model.joblib             
│   │   ├── model_meta.json          
│   │   └── encoders.json            
│   ├── cleaning.py                  
│   ├── loader.py                    
│   ├── cost_engine.py               
│   └── comparison_service.py       
├── api/
│   ├── main.py
│   └── routers/
│       ├── cars.py                  
│       ├── costs.py                
│       ├── reports.py              
│       └── predictions.py           
├── database/
│   ├── models.py
│   ├── connection.py
│   └── create_tables.py
└── config/
    └── settings.py                
```

---

## Setup

### Prerequisites

- Python 3.12+ · PostgreSQL 16+ · [uv](https://github.com/astral-sh/uv)

### Install

```bash
git clone https://github.com/mwandikikepha/car-predictor
cd car-predictor
uv sync
uv run playwright install chromium
```

### Environment

```env
# .env
DB_URL=postgresql://user:password@localhost:5432/japan_cars
MIN_YEAR=2015
MAX_YEAR=2026
USD_TO_KES=130.0
```

### Run the full pipeline

```bash
uv run python database/create_tables.py
uv run python app/scrapers/run_scrapers.py
uv run python app/cleaning.py
uv run python app/loader.py
uv run python app/cost_engine.py
uv run python app/ml/train.py          # ← trains and saves model
uv run uvicorn api.main:app --reload --port 8000
```

---

## API

Base URL: `http://localhost:8000/api` · Docs: `http://localhost:8000/docs`

| Endpoint | Description |
|---|---|
| `GET /predictions/price` | **ML** — fair-price prediction + verdict |
| `GET /predictions/model-info` | Model metrics, top features, training date |
| `GET /costs/compare` | **Core** — Japan landed cost vs Kenya local price |
| `GET /costs/{id}/breakdown` | Full KRA receipt (13 line items) |
| `GET /reports/top-deals` | Best import savings with outlier filtering |
| `GET /reports/top-deals/summary` | Aggregate stats for dashboard header |
| `GET /cars/makes` · `/models` · `/years` | Dropdown data |
| `GET /cars/stats/summary` | Platform-wide counts and averages |

### ML prediction endpoint

```bash
# Is this listing fairly priced?
curl "http://localhost:8000/api/predictions/price?\
make=Toyota&model=Harrier&year=2021\
&mileage_km=30000&fuel_type=Hybrid\
&transmission=Automatic&listing_price_usd=18000"
```

```json
{
  "predicted_price_usd": 17590,
  "predicted_price_kes": "KSh 2,286,700",
  "price_range_usd": { "low": 14592, "high": 20588 },
  "price_range_kes": { "low": "KSh 1,897,000", "high": "KSh 2,676,000" },
  "confidence_note": "±17% based on model accuracy (MAE $2,404)",
  "verdict": "Fair price — within the expected range for this spec.",
  "model_info": { "r2": 0.856, "trained_on": 2294, "trained_at": "2026-05-28" }
}
```

### Comparison endpoint

```bash
curl "http://localhost:8000/api/costs/compare?\
make=Subaru&model=Forester&year=2022"
```

```json
{
  "make": "Subaru",
  "model": "Forester",
  "car": {
    "trim": "Forester Touring",
    "year": 2022,
    "mileage_km": 45000,
    "engine_cc": 2000,
    "fuel": "Petrol",
    "transmission": "Automatic"
  },
  "import_cost": "KSh 3,562,500",
  "local_market": { "price": "KSh 4,800,000", "year": 2022 },
  "verdict": "IMPORT_CHEAPER",
  "difference": "KSh 1,237,500 cheaper to import",
  "verdict_label": "Import",
  "verdict_color": "green"
}
```

---

## Known limitations and next steps

| Limitation | Impact | Fix |
|---|---|---|
 |
| No trim-level data | "Navara" spans $12k–$35k — model averages across trims | Scrape trim field from listings |
| Static exchange rate | KES/USD moves; calculations drift over time | Weekly rate refresh via API |
| No automated retraining | Model goes stale as market changes | Monthly Airflow retraining DAG |
| KRA rates hardcoded | Tax law changes require code edit | Move rates to DB or config |

---

## Roadmap

- [ ] Frontend dashboard (search · compare · KRA receipt · ML predictor)
- [ ] Car From Japan scraper (additional Japan source)
- [ ] Airflow weekly pipeline DAG + monthly retraining
- [ ] Cars45 / PigiaMe Kenya scrapers
- [ ] Docker Compose

---

## Author

**Kepha Mwandiki** — Data Engineer & Data Scientist  
GitHub: [@mwandikikepha](https://github.com/mwandikikepha)

---

## License

MIT
