# diagnose_skips.py
# Run from your project root: uv run python diagnose_skips.py
#
# Loads every raw JSON file and runs each listing through the same
# checks as clean_listing(), but instead of silently dropping it,
# records exactly which rule killed it.

import json
import sys
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config.settings import settings

MIN_YEAR   = settings.MIN_YEAR   # 2018
MAX_YEAR   = settings.MAX_YEAR   # 2026
USD_TO_KES = settings.USD_TO_KES

MAKE_NORMALIZE = {
    "toyota": "Toyota", "honda": "Honda", "nissan": "Nissan",
    "mazda": "Mazda", "subaru": "Subaru", "mitsubishi": "Mitsubishi",
    "suzuki": "Suzuki", "daihatsu": "Daihatsu", "isuzu": "Isuzu",
    "lexus": "Lexus", "infiniti": "Infiniti", "jeep": "Jeep",
    "mercedes-benz": "Mercedes-Benz", "mercedes": "Mercedes-Benz",
    "benz": "Mercedes-Benz", "bmw": "BMW",
    "volkswagen": "Volkswagen", "vw": "Volkswagen",
    "land rover": "Land Rover", "land-rover": "Land Rover",
    "mini": "MINI", "volvo": "Volvo", "ford": "Ford",
    "hyundai": "Hyundai", "kia": "Kia", "peugeot": "Peugeot",
    "audi": "Audi",
}

def normalize_make(make):
    if not make:
        return None
    return MAKE_NORMALIZE.get(make.lower().strip(), make.strip().title())


def diagnose(listing: dict) -> str:
    """Return a skip reason string, or 'OK' if the listing would pass."""

    # ── Year ──────────────────────────────────────────────────────
    year = listing.get("year")
    if year is None:
        return "year=None"
    if not isinstance(year, int):
        return f"year not int ({type(year).__name__}: {year!r})"
    if year < MIN_YEAR:
        return f"year too old ({year} < {MIN_YEAR})"
    if year > MAX_YEAR:
        return f"year too new/invalid ({year} > {MAX_YEAR})"

    # ── Make ──────────────────────────────────────────────────────
    raw_make = listing.get("make")
    make = normalize_make(raw_make)
    if not make:
        return f"make=None/empty (raw: {raw_make!r})"

    # ── Model ─────────────────────────────────────────────────────
    model = listing.get("model")
    if not model:
        return f"model=None/empty"

    # ── Price ─────────────────────────────────────────────────────
    price_original    = listing.get("price")
    original_currency = (listing.get("currency") or "USD").upper()

    if not price_original:
        return f"price=None/zero (currency: {original_currency})"

    if original_currency in ("USD", "US$"):
        price_usd = price_original
    elif original_currency in ("KES", "KSH"):
        price_usd = price_original / USD_TO_KES
    else:
        price_usd = price_original

    if not price_usd:
        return "price_usd resolved to zero/None"

    return "OK"


def load_raw(raw_dir: Path) -> list[tuple[str, dict]]:
    """Return list of (source_name, listing_dict) tuples."""
    all_listings = []
    for json_file in sorted(raw_dir.glob("*.json")):
        if "summary" in json_file.name:
            continue
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        listings = data.get("listings", data if isinstance(data, list) else [])
        source   = json_file.stem.rsplit("_", 2)[0]   # strip timestamp
        for l in listings:
            all_listings.append((source, l))
        print(f"  Loaded {len(listings):>5} from {json_file.name}")
    return all_listings


def main():
    raw_dir = Path("data/raw")
    print(f"\nLoading raw files from {raw_dir}/")
    all_listings = load_raw(raw_dir)
    print(f"Total raw listings: {len(all_listings)}\n")

    # ── Per-source breakdown ───────────────────────────────────────
    source_results: dict[str, Counter] = defaultdict(Counter)
    for source, listing in all_listings:
        reason = diagnose(listing)
        source_results[source][reason] += 1

    print("=" * 70)
    print("SKIP REASONS BY SOURCE")
    print("=" * 70)
    for source, counts in sorted(source_results.items()):
        total  = sum(counts.values())
        passed = counts.get("OK", 0)
        failed = total - passed
        print(f"\n{source}  ({total} raw → {passed} pass, {failed} skip)")
        print(f"  {'Reason':<45} {'Count':>6}  {'%':>5}")
        print(f"  {'-'*45}  {'-'*6}  {'-'*5}")
        for reason, cnt in counts.most_common():
            if reason == "OK":
                continue
            pct = cnt / total * 100
            print(f"  {reason:<45} {cnt:>6}  {pct:>4.1f}%")

    # ── Global rollup ─────────────────────────────────────────────
    global_counts: Counter = Counter()
    for counts in source_results.values():
        global_counts.update(counts)

    total  = sum(global_counts.values())
    passed = global_counts.get("OK", 0)
    failed = total - passed

    print(f"\n{'=' * 70}")
    print(f"GLOBAL SUMMARY  ({total} raw → {passed} pass, {failed} skip)")
    print(f"{'=' * 70}")
    print(f"  {'Reason':<45} {'Count':>6}  {'%':>5}")
    print(f"  {'-'*45}  {'-'*6}  {'-'*5}")
    for reason, cnt in global_counts.most_common():
        if reason == "OK":
            continue
        pct = cnt / total * 100
        print(f"  {reason:<45} {cnt:>6}  {pct:>4.1f}%")

    # ── Sample bad listings for the top skip reason ───────────────
    top_reason = [r for r, _ in global_counts.most_common() if r != "OK"][0]
    samples = [
        listing for source, listing in all_listings
        if diagnose(listing) == top_reason
    ][:5]

    print(f"\n{'=' * 70}")
    print(f"5 SAMPLE LISTINGS HITTING TOP SKIP REASON: '{top_reason}'")
    print(f"{'=' * 70}")
    show_keys = ["source", "make", "model", "year", "price", "currency",
                 "mileage", "fuel_type", "transmission"]
    for i, s in enumerate(samples, 1):
        print(f"\n  Sample {i}:")
        for k in show_keys:
            if k in s:
                print(f"    {k:<14}: {s[k]!r}")

    print()


if __name__ == "__main__":
    main()
