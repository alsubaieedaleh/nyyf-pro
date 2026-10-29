"""Build plan (مخطط) level prices by combining MOJ deals, district trends and land offers.

No open source publishes current deals by plan, or plan boundaries, so this combines three:

  1. MOJ sales for 2023-Q1, the only open MOJ file that names the plan and parcel of each deal.
     It gives each plan's own land price per m² at that time.
  2. The district sold-price median now (last 12 months, from build_moj_market.py) against the
     same district median in 2023-Q1. The ratio carries each plan's 2023 price to today.
  3. Land offers whose text names the plan (Riyadh only, from build_riyadh_offers.py). Their
     points place the plan on the map and give an asking price per m².

Run after build_moj_market.py (and build_riyadh_offers.py for Riyadh). Writes in apps/web/public/data/:
  <slug>-plans.json       per district: plans with deals, prices and an estimate for today
  <slug>-plans.geojson    plans placed on the map from offer points (only where offers name the plan)

Usage:
  python data/pipelines/build_plans.py --moj <dir> --city الرياض --slug riyadh
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_moj_market import (  # noqa: E402
    MAX_AREA_M2,
    MAX_PPM2,
    MAX_RATIO_TO_DISTRICT_MEDIAN,
    MIN_AREA_M2,
    MIN_PPM2,
    OUT,
    DistrictMatcher,
    read_deals,
)

PLAN_QUARTER = (date(2023, 1, 1), date(2023, 3, 31))
MIN_PLAN_DEALS = 3
MIN_DISTRICT_DEALS = 5
# A district's price change since 2023-Q1 is capped so one thin district cannot swing its plans.
GROWTH_RANGE = (0.6, 2.5)
MIN_OFFERS_TO_PLACE = 2
# Offer points further than this from the plan's median point are treated as misplaced.
MAX_OFFER_SPREAD_DEG = 0.03  # about 3 km
LAND = "قطعة أرض"


def single_ppm2(d):
    if d["count"] != 1 or not (MIN_AREA_M2 <= d["area"] <= MAX_AREA_M2):
        return None
    ppm2 = d["price"] / d["area"]
    return ppm2 if MIN_PPM2 <= ppm2 <= MAX_PPM2 else None


def trimmed_median(values):
    """Median after dropping values more than MAX_RATIO_TO_DISTRICT_MEDIAN away from the first median."""
    if not values:
        return None
    m = statistics.median(values)
    kept = [v for v in values if 1 / MAX_RATIO_TO_DISTRICT_MEDIAN <= v / m <= MAX_RATIO_TO_DISTRICT_MEDIAN]
    return statistics.median(kept), len(kept)


def place(points):
    """Median point of the offers, after dropping points far from it. None if too few remain."""
    if len(points) < MIN_OFFERS_TO_PLACE:
        return None
    mx = statistics.median(p[0] for p in points)
    my = statistics.median(p[1] for p in points)
    near = [p for p in points if abs(p[0] - mx) <= MAX_OFFER_SPREAD_DEG and abs(p[1] - my) <= MAX_OFFER_SPREAD_DEG]
    if len(near) < MIN_OFFERS_TO_PLACE:
        return None
    return round(statistics.median(p[0] for p in near), 5), round(statistics.median(p[1] for p in near), 5), len(near)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moj", required=True, type=Path)
    ap.add_argument("--city", default="الرياض")
    ap.add_argument("--slug", default="riyadh")
    args = ap.parse_args()

    districts = json.loads((OUT / f"{args.slug}-districts.geojson").read_text(encoding="utf-8"))["features"]
    by_id = {f["properties"]["id"]: f["properties"] for f in districts}
    match = DistrictMatcher(districts)

    deals = [
        d for d in {d["ref"] or id(d): d for d in read_deals(args.moj, args.city)}.values()
        if PLAN_QUARTER[0] <= d["date"] <= PLAN_QUARTER[1]
    ]

    # District baseline in 2023-Q1, defined like the current district median: residential single deals.
    district_res = defaultdict(list)
    plan_deals = defaultdict(list)
    for d in deals:
        f = match(d["district"])
        if f is None:
            continue
        did = f["properties"]["id"]
        ppm2 = single_ppm2(d)
        if d["class"] == "residential" and ppm2:
            district_res[did].append(ppm2)
        if d["plan"]:
            plan_deals[(did, d["plan"])].append({**d, "ppm2": ppm2})

    offers_by_plan = defaultdict(list)
    offers_path = OUT / f"{args.slug}-offers.geojson"
    if offers_path.exists():
        for o in json.loads(offers_path.read_text(encoding="utf-8"))["features"]:
            if o["properties"].get("plan"):
                offers_by_plan[o["properties"]["plan"]].append(o)

    plans_out = defaultdict(list)
    placed = []
    seen_plans = set()
    for (did, plan), ds in sorted(plan_deals.items(), key=lambda kv: -len(kv[1])):
        district = by_id[did]
        land = trimmed_median([d["ppm2"] for d in ds if d["type"] == LAND and d["ppm2"]])
        land_ppm2, land_n = land if land else (None, 0)
        if land_n < MIN_PLAN_DEALS:
            land_ppm2 = None

        base = trimmed_median(district_res.get(did, []))
        growth = None
        if base and base[1] >= MIN_DISTRICT_DEALS and district["ppm2"]:
            growth = min(max(district["ppm2"] / base[0], GROWTH_RANGE[0]), GROWTH_RANGE[1])

        # Offers are matched by plan number within the city; a plan number is listed once,
        # under the district where it has the most deals.
        offers = offers_by_plan.get(plan, []) if plan not in seen_plans else []
        seen_plans.add(plan)
        asking = [o["properties"]["ppm2"] for o in offers]
        where = place([o["geometry"]["coordinates"] for o in offers])

        row = {
            "plan": plan,
            "deals": len(ds),
            "land_deals": land_n,
            "land_ppm2_2023q1": round(land_ppm2) if land_ppm2 else None,
            "growth": round(growth, 3) if growth else None,
            "ppm2_est": round(land_ppm2 * growth) if land_ppm2 and growth else None,
            "offers": len(offers),
            "asking_ppm2": round(statistics.median(asking)) if len(asking) >= MIN_PLAN_DEALS else None,
            "parcels": sorted({d["parcel"] for d in ds if d.get("parcel")}, key=lambda p: (len(p), p))[:60],
        }
        plans_out[str(did)].append(row)
        if where:
            lng, lat, n = where
            placed.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lng, lat]},
                    "properties": {
                        "id": int(plan) if plan.isdigit() else len(placed) + 1,
                        "plan": plan,
                        "district_id": did,
                        "ppm2_est": row["ppm2_est"],
                        "land_ppm2_2023q1": row["land_ppm2_2023q1"],
                        "asking_ppm2": row["asking_ppm2"],
                        "deals": row["deals"],
                        "offers": n,
                    },
                }
            )

    (OUT / f"{args.slug}-plans.json").write_text(
        json.dumps(plans_out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    if placed:
        (OUT / f"{args.slug}-plans.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": placed}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    meta_path = OUT / "market-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    rows = [r for rs in plans_out.values() for r in rs]
    meta[args.slug]["plans"] = {
        "source_quarter": "2023-Q1",
        "plans": len(rows),
        "with_land_price": sum(1 for r in rows if r["land_ppm2_2023q1"]),
        "with_estimate": sum(1 for r in rows if r["ppm2_est"]),
        "placed": len(placed),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.slug}: {len(deals)} deals in 2023-Q1, plans {meta[args.slug]['plans']}")


if __name__ == "__main__":
    main()
