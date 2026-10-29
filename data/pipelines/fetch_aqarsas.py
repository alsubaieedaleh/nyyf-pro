"""Pull current deals with plan (مخطط) and parcel numbers from the Aqarsas API.

Aqarsas serves Ministry of Justice and Real Estate Registry deals with the plan and parcel of each
deal, and coordinates with the spatial add-on. Docs: https://aqarsas.sa/api. Needs a key from
their support team in the AQARSAS_KEY environment variable (never commit it).

/transactions/ returns at most 5,000 deals per request (a random 5,000 when more match), so the
date range is split in half until each window returns fewer than the cap.

Writes:
  data/raw/aqarsas/<slug>/<start>_<end>.json   raw responses (gitignored), reused on reruns
  <out>/aqarsas-deals.csv.gz                   normalised deals for the base dataset

Usage:
  AQARSAS_KEY=... python data/pipelines/fetch_aqarsas.py --out <dir> --since 2025-04-01
  AQARSAS_KEY=... python data/pipelines/fetch_aqarsas.py --out <dir> --sample   # two Riyadh plans only
"""

import argparse
import csv
import gzip
import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "aqarsas"
API = "https://api.aqarsas.sa"
CAP = 5000
PAUSE_S = 1.0

# slug: (Aqarsas region number, city name). City names must match Aqarsas exactly; check them
# against the first sample and adjust here.
CITIES = {
    "riyadh": (0, "الرياض"),
    "jeddah": (1, "جدة"),
    "makkah": (1, "مكة المكرمة"),
    "madinah": (2, "المدينة المنورة"),
    "dammam": (4, "الدمام"),
    "khobar": (4, "الخبر"),
}

SAMPLE = [("riyadh", "3057"), ("riyadh", "3540")]

FIELDS = [
    "date", "city", "district", "plan", "parcel", "category", "type", "price", "area_m2", "ppm2",
    "source", "abnormal", "lng", "lat", "geo_accuracy",
]


def post(endpoint, body):
    req = urllib.request.Request(
        f"{API}/{endpoint}/",
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        data = json.load(res)
    if data.get("Error_code") != 0:
        raise RuntimeError(f"{endpoint}: {data.get('Error_msg')}")
    time.sleep(PAUSE_S)
    return data


def transactions(key, slug, start, end, **filters):
    """Deals for one city between two dates, cached as raw JSON."""
    state, city = CITIES[slug]
    tag = "_".join([start.isoformat(), end.isoformat(), *(f"{k}-{v}" for k, v in sorted(filters.items()))])
    path = RAW / slug / f"{tag}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    body = {"key": key, "calendar": "gregorian", "state": state, "city": city,
            "start_date": start.isoformat(), "end_date": end.isoformat(), **filters}
    deals = post("transactions", body).get("Deals_list", [])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(deals, ensure_ascii=False), encoding="utf-8")
    return deals


def fetch_window(key, slug, start, end, **filters):
    """Split the window until every piece is under the cap, so no deals are sampled away."""
    deals = transactions(key, slug, start, end, **filters)
    if len(deals) < CAP or start == end:
        if len(deals) >= CAP:
            print(f"warning: {slug} {start} still hits the cap in one day; some deals are missing", file=sys.stderr)
        return deals
    mid = start + (end - start) // 2
    return fetch_window(key, slug, start, mid, **filters) + fetch_window(key, slug, mid + timedelta(days=1), end, **filters)


def row(slug, d):
    lng, lat = d.get("Lng") or "", d.get("Lat") or ""
    return [
        datetime.strptime(d["Date"], "%d/%m/%Y").date().isoformat(), slug, d.get("Hai", ""), d.get("M566", ""),
        d.get("Unit", ""), d.get("Category", ""), d.get("Dtype", ""), d.get("Deal_price", ""), d.get("Area", ""),
        d.get("Meter_price", ""), d.get("Deal_src", ""), d.get("Abnormality_explanation", ""),
        lng if lng != 0 else "", lat if lat != 0 else "", d.get("GAccuracy", ""),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--since", type=date.fromisoformat, default=date.today() - timedelta(days=365))
    ap.add_argument("--until", type=date.fromisoformat, default=date.today())
    ap.add_argument("--cities", default=",".join(CITIES))
    ap.add_argument("--sample", action="store_true", help="only the plans in SAMPLE, to check a trial key")
    args = ap.parse_args()
    key = os.environ.get("AQARSAS_KEY") or sys.exit("Set AQARSAS_KEY")

    rows = []
    if args.sample:
        for slug, plan in SAMPLE:
            deals = fetch_window(key, slug, args.since, args.until, m566=plan, m566_exact_match=1)
            rows += [row(slug, d) for d in deals]
            print(f"{slug} plan {plan}: {len(deals)} deals")
    else:
        for slug in args.cities.split(","):
            deals = fetch_window(key, slug, args.since, args.until)
            rows += [row(slug, d) for d in deals]
            with_xy = sum(1 for d in deals if d.get("Lng"))
            with_plan = sum(1 for d in deals if d.get("M566"))
            print(f"{slug}: {len(deals)} deals, {with_plan} with a plan, {with_xy} with coordinates")

    args.out.mkdir(parents=True, exist_ok=True)
    name = "aqarsas-sample.csv.gz" if args.sample else "aqarsas-deals.csv.gz"
    with gzip.open(args.out / name, "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        w.writerows(rows)
    print(f"{args.out / name}: {len(rows)} deals")


if __name__ == "__main__":
    main()
