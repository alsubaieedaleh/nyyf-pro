"""Export the project's base dataset: clean, joined tables for every city on the map.

Run after build_all.sh has built apps/web/public/data/. Re-reads the MOJ deals so every deal is
kept (not only the ones the map shows) with its district id, plan and parcel where known.

Writes to --out:
  deals.csv.gz       every MOJ sale deal in the six cities, district-matched
  districts.csv      district stats (sold price, change, volume, rent) with a centre point
  districts.geojson  district boundaries for all six cities
  plans.csv          plan (مخطط) prices: 2023-Q1 land price, estimate for today, offers, location
  rents.csv          rent by district and property type (REGA, latest four quarters)
  offers.csv         Riyadh land offers (asking prices) with district and plan

Usage:
  python data/pipelines/build_base.py --moj <dir> --out <dir>
"""

import argparse
import csv
import gzip
import json
import sys
from pathlib import Path

from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_moj_market import OUT, DistrictMatcher, quarter, read_deals  # noqa: E402
from build_plans import single_ppm2  # noqa: E402

CITIES = {
    "riyadh": "الرياض",
    "jeddah": "جدة",
    "makkah": "مكة المكرمة",
    "madinah": "المدينة المنورة",
    "dammam": "الدمام",
    "khobar": "الخبر",
}


def load(name):
    path = OUT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_csv(path, header, rows, opener=open):
    with opener(path, "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moj", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    deal_rows, district_rows, plan_rows, rent_rows, features = [], [], [], [], []
    for slug, city in CITIES.items():
        districts = load(f"{slug}-districts.geojson")["features"]
        names = {f["properties"]["id"]: f["properties"] for f in districts}
        match = DistrictMatcher(districts)

        for d in {d["ref"] or id(d): d for d in read_deals(args.moj, city)}.values():
            f = match(d["district"])
            ppm2 = single_ppm2(d)
            deal_rows.append([
                d["ref"], d["date"].isoformat(), quarter(d["date"]), slug, d["district"],
                f["properties"]["id"] if f else "", d["plan"] or "", d.get("parcel") or "",
                d["class"], d["type"] or "", d["count"], round(d["price"]), round(d["area"], 1),
                round(ppm2) if ppm2 else "",
            ])

        for f in districts:
            p = f["properties"]
            c = shape(f["geometry"]).representative_point()
            district_rows.append([
                slug, p["id"], p["name_ar"], p["name_en"], p["ppm2"] or "", p["yoy"] if p["yoy"] is not None else "",
                p["deals_12m"], p["value_12m"], p["deals_total"], p["last_deal"] or "",
                p.get("rent_apt") or "", p.get("rent_apt_m2") or "", round(c.x, 5), round(c.y, 5),
            ])
            features.append({**f, "properties": {"city": slug, "id": p["id"], "name_ar": p["name_ar"], "name_en": p["name_en"]}})

        placed = {
            (g["properties"]["district_id"], g["properties"]["plan"]): g["geometry"]["coordinates"]
            for g in (load(f"{slug}-plans.geojson") or {"features": []})["features"]
        }
        for did, plans in (load(f"{slug}-plans.json") or {}).items():
            for r in plans:
                lng, lat = placed.get((int(did), r["plan"]), ("", ""))
                plan_rows.append([
                    slug, did, names[int(did)]["name_ar"], r["plan"], r["deals"], r["land_deals"],
                    r["land_ppm2_2023q1"] or "", r["growth"] or "", r["ppm2_est"] or "",
                    r["offers"], r["asking_ppm2"] or "", lng, lat, " ".join(r["parcels"]),
                ])

        for did, types in (load(f"{slug}-rent.json") or {}).items():
            for t, r in types.items():
                rent_rows.append([slug, did, names[int(did)]["name_ar"], t, r["contracts"], r["rent"], r["rent_m2"] or ""])

    n = {
        "deals": write_csv(
            args.out / "deals.csv.gz",
            ["ref", "date", "quarter", "city", "district_raw", "district_id", "plan", "parcel",
             "class", "type", "properties", "price", "area_m2", "ppm2"],
            deal_rows, gzip.open,
        ),
        "districts": write_csv(
            args.out / "districts.csv",
            ["city", "district_id", "name_ar", "name_en", "ppm2_12m", "yoy", "deals_12m", "value_12m",
             "deals_total", "last_deal", "rent_apt_year", "rent_apt_m2_year", "lng", "lat"],
            district_rows,
        ),
        "plans": write_csv(
            args.out / "plans.csv",
            ["city", "district_id", "district_ar", "plan", "deals_2023q1", "land_deals_2023q1",
             "land_ppm2_2023q1", "district_growth", "ppm2_est_now", "offers", "asking_ppm2", "lng", "lat", "parcels"],
            plan_rows,
        ),
        "rents": write_csv(
            args.out / "rents.csv",
            ["city", "district_id", "district_ar", "type", "contracts", "rent_year", "rent_m2_year"],
            rent_rows,
        ),
    }
    offers = load("riyadh-offers.geojson")["features"]
    n["offers"] = write_csv(
        args.out / "offers.csv",
        ["id", "city", "lng", "lat", "price", "area_m2", "ppm2", "district_id", "plan"],
        [[o["properties"]["id"], "riyadh", *o["geometry"]["coordinates"], o["properties"]["price"], o["properties"]["area"],
          o["properties"]["ppm2"], o["properties"]["district_id"] or "", o["properties"].get("plan") or ""] for o in offers],
    )
    with open(args.out / "districts.geojson", "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, ensure_ascii=False, separators=(",", ":"))
    print(n)


if __name__ == "__main__":
    main()
