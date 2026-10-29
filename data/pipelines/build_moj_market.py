"""Build district market data from Ministry of Justice (MOJ) sale deals.

Inputs (both open data, see docs/06-data-model.md → "Data sources"):
  --moj        folder of MOJ quarterly sales CSVs (MOJ-Sales-YYYY-Qn.csv[.gz]), as mirrored in
               https://github.com/civillizard/saudi-real-estate-data (moj/sales/)
  --districts  districts.geojson with National Address district boundaries, as mirrored in
               https://github.com/homaily/Saudi-Arabia-Regions-Cities-and-Districts (geojson/)

Outputs in apps/web/public/data/:
  <slug>-districts.geojson         district polygons with sold-price stats
  <slug>-deals/<district_id>.json  recent deals and the quarterly price series per district
  market-meta.json                 coverage, data window, and match rate per city

Usage:
  python data/pipelines/build_moj_market.py --moj <dir> --districts <file> --city الرياض --slug riyadh
"""

import argparse
import csv
import gzip
import json
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "apps" / "web" / "public" / "data"

# Price per m² stats use single-property deals only; bulk deals split one price over many plots.
MIN_AREA_M2 = 50
MAX_AREA_M2 = 2_000_000
MIN_PPM2 = 20
MAX_PPM2 = 100_000
# Deals further than this from the district median (as a ratio) are dropped as outliers.
MAX_RATIO_TO_DISTRICT_MEDIAN = 5
MIN_DEALS_FOR_STATS = 5
RECENT_DEALS_PER_DISTRICT = 40

# MOJ spellings that differ from the National Address names (after normalise()).
# Ambiguous names (النسيم and ام الحمام without east/west) and areas that are not districts
# (شرق الرياض, طريق الحجاز) are left unmatched on purpose.
ALIASES = {
    "الصفاء": "الصفا",
    "الشفاء": "الشفا",
    "المعيزليه": "المعيزله",
    "سدره": "السدره",
    "غبيراء": "غبيره",
    "اشبيليا": "اشبيليه",
    "مطار الملك خالد الدولي": "مطار الملك خالد",
    # REGA rental spellings
    "غبيرا": "غبيره",
    "المعيزيله": "المعيزله",
    "العريجاء الاوسط": "العريجاء الوسطي",
    "مغرزات": "المغرزات",
}

CLASSES = {"سكني": "residential", "تجاري": "commercial", "زراعي": "agricultural", "صناعي": "industrial"}


def normalise(name: str) -> str:
    """Make MOJ and National Address district names comparable."""
    s = name.strip()
    s = re.sub(r"^.*?/\s*", "", s) if "/" in s else s  # "الرياض/ حي الملقا" → "حي الملقا"
    s = re.sub(r"[أإآ]", "ا", s)
    s = s.replace("ة", "ه").replace("ى", "ي").replace("ـ", "")
    s = re.sub(r"^(حي|حى)\s*", "", s)
    s = re.sub(r"^\d+\s*(حي|حى)?\s*", "", s)  # MOJ sometimes prefixes a code: "827 حى هجرة"
    s = s.replace("عبد ال", "عبدال")
    s = re.sub(r"\s+", " ", s).strip()
    return ALIASES.get(s, s)


def simplify_name(name: str) -> str:
    """Drop qualifiers MOJ adds to municipal names: "الشامية الجديد", "طيبة بمنطقة البيداء"."""
    s = re.split(r"\s+(?:ب|في |فى )?منطقه\s|\s+مخطط\s|\s+(?:شرق|غرب|شمال|جنوب) طريق\s", name)[0]
    s = re.sub(r"\s+(الجديد|الجديده|هـ|ه)$", "", s)
    return s.strip()


class DistrictMatcher:
    """Match a district name to a boundary: exact, then simplified, then a unique word-boundary prefix."""

    def __init__(self, features, name=lambda f: f["properties"]["name_ar"]):
        self.exact = {normalise(name(f)): f for f in features}
        self.cache = {}

    def __call__(self, raw: str):
        if raw in self.cache:
            return self.cache[raw]
        key = normalise(raw)
        f = self.exact.get(key)
        if f is None:
            short = simplify_name(key)
            f = self.exact.get(short)
            if f is None and len(short) >= 4:
                hits = [v for k, v in self.exact.items() if k == short or k.startswith(short + " ") or short.startswith(k + " ")]
                f = hits[0] if len(hits) == 1 else None
        self.cache[raw] = f
        return f


def same_city(a: str, b: str) -> bool:
    """MOJ and REGA spell some cities differently from the National Address (جده vs جدة)."""
    fold = lambda s: s.strip().replace("ة", "ه").replace("أ", "ا")
    return fold(a) == fold(b)


def number(value: str):
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def parse_date(value: str):
    value = value.strip()
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})$", value)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})$", value)  # 2023 Q1 uses M/D/YYYY
    if m:
        return date(int(m[3]), int(m[1]), int(m[2]))
    return None


def read_deals(moj_dir: Path, city: str):
    """Yield normalised deals for one city from every quarterly file (two schemas over the years)."""
    for path in sorted(moj_dir.glob("MOJ-Sales-20*.csv*")):
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                row = {k.strip(): v for k, v in row.items() if k}
                if not same_city(row.get("المدينة", ""), city):
                    continue
                district = row.get("المدينة / الحي") or row.get("الحي") or ""
                when = parse_date(row.get("تاريخ الصفقة ميلادي") or row.get("التاريخ") or "")
                price = number(row.get("السعر") or row.get("السعر بالريال السعودي") or "")
                area = number(row.get("المساحة") or "")
                count = number(row.get("عدد العقارات") or "1") or 1
                if not when or not price or not area:
                    continue
                plan = (row.get("المخطط") or "").replace("مخطط/", "").strip()
                yield {
                    "ref": (row.get("الرقم المرجعي للصفقة") or row.get("رقم مرجعي") or "").strip(),
                    "district": district.replace("حي/", "").strip(),
                    "date": when,
                    "class": CLASSES.get(row.get("تصنيف العقار", "").strip(), "other"),
                    "type": (row.get("نوع العقار") or "").strip() or None,
                    "plan": plan if plan and plan != "أخرى" else None,
                    "parcel": re.sub(r"^\s*قطعة\s*", "", row.get("رقم القطعة") or "").strip() or None,
                    "count": int(count),
                    "price": price,
                    "area": area,
                }


def unary_bbox(features):
    xs0, ys0, xs1, ys1 = zip(*(shape(f["geometry"]).bounds for f in features))
    return min(xs0), min(ys0), max(xs1), max(ys1)


def quarter(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moj", required=True, type=Path)
    ap.add_argument("--districts", required=True, type=Path)
    ap.add_argument("--city", default="الرياض", help="city name as written in the National Address data")
    ap.add_argument("--city-en", default="Riyadh")
    ap.add_argument("--slug", default="riyadh")
    args = ap.parse_args()

    with open(args.districts, encoding="utf-8") as fh:
        all_districts = json.load(fh)["features"]
    with open(args.districts.parent.parent / "json" / "cities_lite.json", encoding="utf-8") as fh:
        city_id = next(c["city_id"] for c in json.load(fh) if same_city(c["name_ar"], args.city))
    districts = [f for f in all_districts if f["properties"]["city_id"] == city_id]
    match = DistrictMatcher(districts)

    deals = list({d["ref"] or id(d): d for d in read_deals(args.moj, args.city)}.values())
    latest = max(d["date"] for d in deals)
    window_start = latest - timedelta(days=364)
    prev_start = window_start - timedelta(days=365)

    matched = defaultdict(list)
    unmatched = defaultdict(int)
    for d in deals:
        f = match(d["district"])
        if f is None:
            unmatched[d["district"]] += 1
            continue
        d["ppm2"] = d["price"] / d["area"] if d["count"] == 1 else None
        if d["ppm2"] is not None and not (
            MIN_AREA_M2 <= d["area"] <= MAX_AREA_M2 and MIN_PPM2 <= d["ppm2"] <= MAX_PPM2
        ):
            d["ppm2"] = None
        matched[f["properties"]["district_id"]].append(d)

    out_features = []
    deals_dir = OUT / f"{args.slug}-deals"
    deals_dir.mkdir(parents=True, exist_ok=True)
    for f in districts:
        p = f["properties"]
        ds = matched.get(p["district_id"], [])
        res = [d for d in ds if d["class"] == "residential" and d["ppm2"]]
        med_all = statistics.median([d["ppm2"] for d in res]) if res else None
        if med_all:
            res = [d for d in res if 1 / MAX_RATIO_TO_DISTRICT_MEDIAN <= d["ppm2"] / med_all <= MAX_RATIO_TO_DISTRICT_MEDIAN]
        last12 = [d["ppm2"] for d in res if d["date"] >= window_start]
        prev12 = [d["ppm2"] for d in res if prev_start <= d["date"] < window_start]
        ppm2 = round(statistics.median(last12)) if len(last12) >= MIN_DEALS_FOR_STATS else None
        prev = statistics.median(prev12) if len(prev12) >= MIN_DEALS_FOR_STATS else None

        series = defaultdict(list)
        for d in res:
            series[quarter(d["date"])].append(d["ppm2"])
        trend = [
            [q, round(statistics.median(v)), len(v)]
            for q, v in sorted(series.items())
            if len(v) >= 3
        ]
        recent = sorted(ds, key=lambda d: d["date"], reverse=True)[:RECENT_DEALS_PER_DISTRICT]
        deals_12m = [d for d in ds if d["date"] >= window_start]

        props = {
            "id": p["district_id"],
            "name_ar": p["name_ar"],
            "name_en": p["name_en"],
            "ppm2": ppm2,
            "yoy": round((ppm2 - prev) / prev, 3) if ppm2 and prev else None,
            "deals_12m": len(deals_12m),
            "value_12m": round(sum(d["price"] for d in deals_12m)),
            "deals_total": len(ds),
            "last_deal": max((d["date"] for d in ds), default=None),
        }
        if props["last_deal"]:
            props["last_deal"] = props["last_deal"].isoformat()
        out_features.append(
            {
                "type": "Feature",
                "id": p["district_id"],
                "geometry": shape(f["geometry"]).simplify(0.0002).__geo_interface__,
                "properties": props,
            }
        )
        with open(deals_dir / f"{p['district_id']}.json", "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "trend": trend,
                    "recent": [
                        {
                            "date": d["date"].isoformat(),
                            "price": round(d["price"]),
                            "area": round(d["area"], 1),
                            "ppm2": round(d["ppm2"]) if d["ppm2"] else None,
                            "class": d["class"],
                            "type": d["type"],
                            "plan": d["plan"],
                            "count": d["count"],
                        }
                        for d in recent
                    ],
                },
                fh,
                ensure_ascii=False,
                separators=(",", ":"),
            )

    path = OUT / f"{args.slug}-districts.geojson"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": out_features}, fh, ensure_ascii=False, separators=(",", ":"))

    total = len(deals)
    city_12m = [d for d in deals if d["date"] >= window_start]
    city_res = [
        d["price"] / d["area"]
        for d in city_12m
        if d["class"] == "residential" and d["count"] == 1 and MIN_AREA_M2 <= d["area"] <= MAX_AREA_M2
        and MIN_PPM2 <= d["price"] / d["area"] <= MAX_PPM2
    ]
    matched_n = sum(len(v) for v in matched.values())
    meta_path = OUT / "market-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta[args.slug] = {
        "city_ar": args.city,
        "city_en": args.city_en,
        "source": "Ministry of Justice (MOJ) open data, KSA Open Data License",
        "first_deal": min(d["date"] for d in deals).isoformat(),
        "last_deal": latest.isoformat(),
        "window_start": window_start.isoformat(),
        "deals": total,
        "matched_deals": matched_n,
        "districts": len(districts),
        "bbox": [round(v, 4) for v in unary_bbox(districts)],
        "districts_with_price": sum(1 for f in out_features if f["properties"]["ppm2"]),
        "median_ppm2_12m": round(statistics.median(city_res)) if city_res else None,
        "deals_12m": len(city_12m),
        "value_12m": round(sum(d["price"] for d in city_12m)),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{args.city_en}: {total} deals {meta[args.slug]['first_deal']}..{latest}, matched {matched_n / total:.1%}")
    print(f"districts {len(districts)}, with 12-month price {meta[args.slug]['districts_with_price']}")
    top = sorted(unmatched.items(), key=lambda kv: -kv[1])[:25]
    print("top unmatched:", top)


if __name__ == "__main__":
    main()
