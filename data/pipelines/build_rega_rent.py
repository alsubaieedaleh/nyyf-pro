"""Add district rent indicators from REGA (Ejar contracts) to the market data.

Input: REGA quarterly rental indicator CSVs for a region (Rental-indicators-in-<Region>-*.csv), as
mirrored in https://github.com/civillizard/saudi-real-estate-data (rega/quarterlies/rental/).
Each row is one district × property type × quarter with contract count, average annual rent
and average annual rent per m².

Run after build_moj_market.py. Updates in apps/web/public/data/:
  <slug>-districts.geojson   adds rent_apt (average annual apartment rent) and rent_apt_m2
  <slug>-rent.json           per district: rent by property type over the latest four quarters
  market-meta.json           adds the rent data window

Usage:
  python data/pipelines/build_rega_rent.py --rent <dir> --region Riyadh --city الرياض --slug riyadh
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_moj_market import OUT, DistrictMatcher, same_city  # noqa: E402

QUARTERS_USED = 4
MIN_CONTRACTS = 5

TYPES = {
    "شقة": "apartment",
    "فيلا": "villa",
    "دور": "floor",
    "استديو": "studio",
    "دوبلاكس": "duplex",
    "محل": "shop",
    "مكتب": "office",
    "معرض تجاري": "showroom",
}


def number(value):
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rent", required=True, type=Path)
    ap.add_argument("--region", default="Riyadh", help="region part of the REGA file names (Riyadh, Makkah, Madinah, EP)")
    ap.add_argument("--city", default="الرياض")
    ap.add_argument("--slug", default="riyadh")
    args = ap.parse_args()

    rows = []
    for path in args.rent.glob(f"Rental-indicators-in-{args.region}*.csv"):
        with open(path, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                # Header spelling changes between quarters ("متوسط الايجار  ر.س" vs "متوسط الايجار").
                row = {re.sub(r"\s+", " ", k.replace("ر.س", "")).strip(): (v or "").strip() for k, v in row.items() if k}
                if not same_city(row.get("المدينة", ""), args.city) or row.get("نوع العقار") not in TYPES:
                    continue
                contracts = number(row.get("عدد الصفقات"))
                rent = number(row.get("متوسط الايجار"))
                rent_m2 = number(row.get("متوسط الايجار لكل متر مربع"))
                if not contracts or not rent:
                    continue
                rows.append(
                    {
                        "quarter": (int(row["السنة"]), int(row["الربع"])),
                        "district": row["الحي"],
                        "type": TYPES[row["نوع العقار"]],
                        "contracts": contracts,
                        "rent": rent,
                        "rent_m2": rent_m2,
                    }
                )

    quarters = sorted({r["quarter"] for r in rows})[-QUARTERS_USED:]
    rows = [r for r in rows if r["quarter"] in quarters]

    districts_path = OUT / f"{args.slug}-districts.geojson"
    collection = json.loads(districts_path.read_text(encoding="utf-8"))
    match = DistrictMatcher(collection["features"])

    # Contract-weighted averages over the quarters used.
    sums = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]))
    unmatched = defaultdict(float)
    for r in rows:
        f = match(r["district"])
        if f is None:
            unmatched[r["district"]] += r["contracts"]
            continue
        s = sums[f["properties"]["id"]][r["type"]]
        s[0] += r["contracts"]
        s[1] += r["rent"] * r["contracts"]
        if r["rent_m2"]:
            s[2] += r["rent_m2"] * r["contracts"]
            s[3] += r["contracts"]

    rent_out = {}
    for f in collection["features"]:
        p = f["properties"]
        types = {
            t: {
                "contracts": int(c),
                "rent": round(total / c),
                "rent_m2": round(total_m2 / c_m2) if c_m2 else None,
            }
            for t, (c, total, total_m2, c_m2) in sums.get(p["id"], {}).items()
            if c >= MIN_CONTRACTS
        }
        apt = types.get("apartment")
        p["rent_apt"] = apt["rent"] if apt else None
        p["rent_apt_m2"] = apt["rent_m2"] if apt else None
        if types:
            rent_out[str(p["id"])] = types

    districts_path.write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / f"{args.slug}-rent.json").write_text(json.dumps(rent_out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    meta_path = OUT / "market-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta[args.slug]["rent_source"] = "Real Estate General Authority (REGA) rental indicators, KSA Open Data License"
    meta[args.slug]["rent_quarters"] = [f"{y}-Q{q}" for y, q in quarters]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(r["contracts"] for r in rows) or 1
    print(f"{args.region}: {int(total)} contracts in {meta[args.slug]['rent_quarters']}, "
          f"matched {1 - sum(unmatched.values()) / total:.1%}, districts with rent {len(rent_out)}")
    print("top unmatched:", sorted(unmatched.items(), key=lambda kv: -kv[1])[:15])


if __name__ == "__main__":
    main()
