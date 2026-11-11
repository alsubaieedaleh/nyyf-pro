"""District sale prices by property type (land, villa, apartment, ...) from REGA sales indicators.

MOJ's open deal files stopped giving the property type after 2023-Q3, so a district price from them mixes
land, villas and apartments. REGA's quarterly "sales transaction indicators" (Real Estate Registry deeds,
open data) give, per district × property type × quarter: deed count, total value, total area and the
average price per m². This script turns them into one price per district and type.

Input: the REGA sales CSVs as mirrored in https://github.com/civillizard/saudi-real-estate-data
(rega/quarterlies/sales/). Two layouts exist: district level (2024 to 2025-Q3 for most regions) and city
level (later quarters). District prices use the district files; the city series uses both.

Writes to --out:
  sales_by_type.csv      district_id, city, type, deeds, ppm2, change vs a year earlier, window, confidence
  market_quarterly.csv   city × type × quarter: deeds, value, area, average price per m²

Usage:
  python data/pipelines/build_rega_sales.py --sales <mirror>/rega/quarterlies/sales \\
      --districts <base>/districts.geojson --out <base>
"""

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_moj_market import DistrictMatcher, number, same_city  # noqa: E402
from cities import CITY_AR  # noqa: E402

CITIES = CITY_AR

# REGA property type -> our type. Commercial and agricultural land are left out.
TYPES = {
    "أرض": "land",
    "قطعة أرض-سكنى": "land",
    "فيلا": "villa",
    "شقة": "apartment",
    "دوبلكس": "duplex",
    "دور": "floor",
}
RESIDENTIAL = {"", "سكني", "nan"}

QUARTERS_USED = 4
PPM2_BOUNDS = {"land": (20, 60000), "default": (300, 100000)}
OUTLIER_X = 5
CONF = [(30, "high"), (10, "medium"), (5, "low")]  # registry deeds behind a price


def header_map(cols):
    """Map the varying REGA headers to fixed names."""
    m = {}
    for i, c in enumerate(c.strip() for c in cols):
        if c == "السنة":
            m["year"] = i
        elif c == "الربع" and "q" not in m:
            m["q"] = i
        elif c == "المدينة":
            m["city"] = i
        elif c == "الحي":
            m["district"] = i
        elif c in ("نوع العقار", "النوع"):
            m["type"] = i
        elif c in ("تصنيف العقار", "الاستخدام"):
            m["cls"] = i
        elif c.startswith("عدد"):
            m["deeds"] = i
        elif c.startswith("مجموع سعر") or c.startswith("قيمة") or c.startswith("مجموع قيم"):
            m["value"] = i
        elif c.startswith("المساحة") or c.startswith("مجموع المساحات"):
            m["area"] = i
        elif c.startswith("متوسط"):
            m["ppm2"] = i
    return m


def read_rows(sales_dir: Path):
    for path in sorted(sales_dir.glob("*.csv")):
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            m = header_map(next(reader))
            for row in reader:
                if len(row) < len(m):
                    continue
                get = lambda k: row[m[k]].strip() if k in m and m[k] < len(row) else ""
                t = TYPES.get(get("type"))
                if not t or get("cls") not in RESIDENTIAL:
                    continue
                year, q = number(get("year")), number(get("q"))
                deeds = number(get("deeds")) or 0
                value, area, avg = number(get("value")), number(get("area")), number(get("ppm2"))
                if not year or not q or deeds <= 0:
                    continue
                ppm2 = avg if avg and avg > 0 else (value / area if value and area else None)
                lo, hi = PPM2_BOUNDS.get(t, PPM2_BOUNDS["default"])
                if ppm2 is not None and not lo <= ppm2 <= hi:
                    ppm2 = None
                yield {
                    "quarter": f"{int(year)}-Q{int(q)}",
                    "city": get("city"),
                    "district": get("district") if "district" in m else None,
                    "type": t,
                    "deeds": deeds,
                    "value": value or 0,
                    "area": area or 0,
                    "ppm2": ppm2,
                }


def slug_of(city):
    for slug, ar in CITIES.items():
        if same_city(city, ar):
            return slug
    return None


def wmean(pairs):
    pairs = [(v, w) for v, w in pairs if v is not None and w > 0]
    tw = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / tw if tw else None


def ratio(rows):
    """Price per m2 as total value / total area over rows with a sane price; REGA's own average is a mean of
    means and is empty for small cells, so it is only the fallback when value or area is missing."""
    ok = [x for x in rows if x["ppm2"]]
    v, a = sum(x["value"] for x in ok), sum(x["area"] for x in ok)
    if v > 0 and a > 0:
        return v / a
    return wmean([(x["ppm2"], x["deeds"]) for x in ok])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sales", required=True, type=Path)
    ap.add_argument("--districts", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    feats = json.loads(args.districts.read_text(encoding="utf-8"))["features"]
    matchers = {s: DistrictMatcher([f for f in feats if f["properties"]["city"] == s]) for s in CITIES}

    district_rows, city_rows = [], []
    for r in read_rows(args.sales):
        slug = slug_of(r["city"])
        if not slug:
            continue
        r["slug"] = slug
        (district_rows if r["district"] else city_rows).append(r)

    # ---- City series: city-level files as given, district files summed ----
    series = {}
    for r in city_rows:
        series[(r["slug"], r["type"], r["quarter"])] = {
            "deeds": r["deeds"], "value": r["value"], "area": r["area"], "ppm2": r["ppm2"]}
    acc = defaultdict(list)
    for r in district_rows:
        acc[(r["slug"], r["type"], r["quarter"])].append(r)
    for key, rows in acc.items():
        if key in series:
            continue
        series[key] = {
            "deeds": sum(x["deeds"] for x in rows),
            "value": sum(x["value"] for x in rows),
            "area": sum(x["area"] for x in rows),
            "ppm2": wmean([(x["ppm2"], x["deeds"]) for x in rows]),
        }

    # ---- District prices per type ----
    med = defaultdict(list)
    for r in district_rows:
        if r["ppm2"]:
            med[(r["slug"], r["type"], r["quarter"])].append(r["ppm2"])
    med = {k: statistics.median(v) for k, v in med.items()}

    by_unit = defaultdict(list)
    unmatched = defaultdict(int)
    for r in district_rows:
        f = matchers[r["slug"]](r["district"])
        if f is None:
            unmatched[r["slug"]] += r["deeds"]
            continue
        m = med.get((r["slug"], r["type"], r["quarter"]))
        if r["ppm2"] and m and not m / OUTLIER_X <= r["ppm2"] <= m * OUTLIER_X:
            r = {**r, "ppm2": None}
        by_unit[(r["slug"], f["properties"]["id"], r["type"])].append(r)

    city_quarters = defaultdict(set)
    for r in district_rows:
        city_quarters[r["slug"]].add(r["quarter"])

    out = []
    for (slug, did, t), rows in sorted(by_unit.items()):
        qs = sorted(city_quarters[slug])[-QUARTERS_USED:]
        recent = [x for x in rows if x["quarter"] in qs]
        deeds = sum(x["deeds"] for x in recent if x["ppm2"])
        ppm2 = ratio(recent)
        # Change: the latest quarters against the same quarters a year earlier.
        latest_year = max(int(q[:4]) for q in qs)
        this = [x for x in rows if x["quarter"].startswith(str(latest_year))]
        same_q = {x["quarter"][4:] for x in this}
        prev = [x for x in rows if x["quarter"].startswith(str(latest_year - 1)) and x["quarter"][4:] in same_q]
        a, b = ratio(this), ratio(prev)
        n_a = sum(x["deeds"] for x in this if x["ppm2"])
        n_b = sum(x["deeds"] for x in prev if x["ppm2"])
        change = round(a / b - 1, 3) if a and b and n_a >= 20 and n_b >= 20 else None
        conf = next((c for n, c in CONF if deeds >= n), "none")
        if ppm2 is None or conf == "none":
            ppm2, conf = None, "none"
        out.append({
            "city": slug, "district_id": did, "type": t, "deeds": int(deeds),
            "ppm2": round(ppm2) if ppm2 else "", "change": "" if change is None else change,
            "window": f"{qs[0]}..{qs[-1]}", "confidence": conf,
        })

    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "sales_by_type.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    # District x type x quarter, for the quarterly report.
    with open(args.out / "sales_district_quarterly.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["city", "district_id", "type", "quarter", "deeds", "value", "area", "ppm2"])
        for (slug, did, t), rows in sorted(by_unit.items()):
            per_q = defaultdict(list)
            for x in rows:
                per_q[x["quarter"]].append(x)
            for q, xs in sorted(per_q.items()):
                p = ratio(xs)
                w.writerow([slug, did, t, q, int(sum(x["deeds"] for x in xs)), round(sum(x["value"] for x in xs)),
                            round(sum(x["area"] for x in xs)), round(p) if p else ""])
    with open(args.out / "market_quarterly.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["city", "type", "quarter", "deeds", "value", "area", "ppm2"])
        for (slug, t, q), s in sorted(series.items()):
            w.writerow([slug, t, q, int(s["deeds"]), round(s["value"]), round(s["area"]),
                        round(s["ppm2"]) if s["ppm2"] else ""])

    for slug in CITIES:
        rows = [o for o in out if o["city"] == slug]
        total = sum(r["deeds"] for r in district_rows if r["slug"] == slug)
        print(f"{slug:8} window {sorted(city_quarters[slug])[-QUARTERS_USED:][0] if city_quarters[slug] else '-'}"
              f"..{max(city_quarters[slug]) if city_quarters[slug] else '-'}  "
              + "  ".join(f"{t} {sum(1 for r in rows if r['type'] == t and r['ppm2'] != '')}"
                          for t in ("land", "villa", "apartment"))
              + f"  unmatched deeds {unmatched[slug]}/{int(total)}")


if __name__ == "__main__":
    main()
