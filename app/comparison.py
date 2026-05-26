# app/comparison.py

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session
from database.connection import engine
from app.comparison_service import get_comparisons, count_comparisons


def _fmt(value) -> str:
    if value is None:
        return "N/A"
    return f"KSh {float(value):>12,.0f}"


def print_comparisons(
    make: str | None = None,
    model: str | None = None,
    year: int | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    limit: int = 30,
):
    with Session(engine) as db:
        total = count_comparisons(db, make=make, model=model,
                                  year_min=year_min, year_max=year_max)
        rows  = get_comparisons(db, make=make, model=model,
                                year=year, year_min=year_min, year_max=year_max,
                                limit=limit)

    if not rows:
        print("No results found.")
        return

    print(f"\n{'='*100}")
    title = "Japan Import vs Kenya Local — Comparison Results"
    if make:  title += f" · {make}"
    if model: title += f" {model}"
    print(f"  {title}")
    print(f"  Showing {len(rows)} of {total} matching Japan listings")
    print(f"{'='*100}")

    header = (
        f"{'Make':<12} {'Model':<28} {'Year':>4}  "
        f"{'Import cost':>14}  {'Local price':>14}  "
        f"{'Savings':>14}  Verdict"
    )
    print(header)
    print("-" * 100)

    counters = {"IMPORT_CHEAPER": 0, "LOCAL_CHEAPER": 0, "NO_LOCAL_DATA": 0}

    for r in rows:
        recommendation = r.get("recommendation", "NO_LOCAL_DATA")
        counters[recommendation] = counters.get(recommendation, 0) + 1

        savings_kes = r.get("savings_kes")
        if savings_kes is None:
            verdict_str = "No local data"
        elif savings_kes > 0:
            verdict_str = f"Import saves {_fmt(savings_kes)}"
        else:
            verdict_str = f"Local saves  {_fmt(abs(savings_kes))}"

        print(
            f"{r['make']:<12} "
            f"{r['model']:<28} "
            f"{r['year']:>4}  "
            f"{_fmt(r.get('import_cost_kes')):>14}  "
            f"{_fmt(r.get('kenya_price_kes')):>14}  "
            f"{_fmt(savings_kes):>14}  "
            f"{verdict_str}"
        )

    print("-" * 100)
    print(
        f"  Import cheaper: {counters['IMPORT_CHEAPER']}  |  "
        f"Local cheaper: {counters['LOCAL_CHEAPER']}  |  "
        f"No local data: {counters['NO_LOCAL_DATA']}"
    )
    print(f"{'='*100}\n")


if __name__ == "__main__":
    
    print_comparisons(make="Toyota", limit=30)
    print_comparisons(make="Subaru", model="Forester", limit=20)