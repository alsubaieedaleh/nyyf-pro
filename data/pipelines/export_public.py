"""Export the public district price map data from the final dataset, behind quality gates.

Reads price_index.geojson and rents_wide.csv from build_final.py, and sales_by_type.csv and
market_quarterly.csv from build_rega_sales.py, and writes the files the public site loads:

  districts.geojson  one simplified polygon per district with, per property type, the sale price per m²
                     (land, villa, apartment; REGA registry deeds), the yearly rent per m² and per unit
                     (apartment, studio, villa, floor; REGA Ejar contracts), and the all-residential MOJ
                     price with its range
  meta.json          data dates, per-city colour breaks for every metric, bounds, coverage, sources
  market.json        home page stats: per city and type, quarterly deals and price per m², rents,
                     most expensive and most active districts

Only district rows from open sources go out (MOJ deals, REGA rents, district polygons). Plans (مخططات)
and the old offers stay private: the offers are not ours to republish.

Before writing, the new data is checked against the last published meta.json. The run stops with
exit code 1 and leaves the published files untouched when, for any city:

  - priced districts fall by more than 5%,
  - the median price per m² moves by more than 15%,
  - a district has a low end above its price, or no name.

Use --force to publish anyway (after a person has checked the change).

Usage:
  python data/pipelines/export_public.py --final <final dir> --base <base dir> \
      --out apps/heatmap/public/data [--force]
"""

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

from shapely.geometry import mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cities import CITY_LIST  # noqa: E402

CITIES = [(c["slug"], c["ar"], c["en"]) for c in CITY_LIST]
MIN_CONFIDENT = 15  # districts with a high or medium confidence price needed to publish a city
MIN_MATCH = 0.6  # share of a city's registry deeds that must match a district polygon

# Map metrics: key -> (mode, type). Sale types come from REGA registry deeds, rents from Ejar contracts.
METRICS = {
    "sale_land": ("sale", "land"),
    "sale_villa": ("sale", "villa"),
    "sale_apartment": ("sale", "apartment"),
    "rent_apartment": ("rent", "apartment"),
    "rent_villa": ("rent", "villa"),
    "rent_floor": ("rent", "floor"),
    "rent_studio": ("rent", "studio"),
    # Average annual rent per contract (per unit; unit sizes vary), the number brokers and tenants quote.
    "rent_apartment_year": ("rent", "apartment"),
    "rent_villa_year": ("rent", "villa"),
    "rent_floor_year": ("rent", "floor"),
    "rent_studio_year": ("rent", "studio"),
}
RENT_TYPES = ("apartment", "villa", "floor", "studio")
WEB_META = Path(__file__).resolve().parents[2] / "apps" / "web" / "public" / "data" / "market-meta.json"
RENT_CONF = [(50, "high"), (15, "medium"), (5, "low")]
SALE_TYPES = ("land", "villa", "apartment", "duplex", "floor")

SOURCES = [
    {
        "id": "moj_deals",
        "ar": "وزارة العدل: صفقات البيع العقارية (البيانات المفتوحة)",
        "en": "Ministry of Justice: real estate sales (open data)",
        "license": "KSA Open Data License",
        "url": "https://open.data.gov.sa",
    },
    {
        "id": "rega_rent",
        "ar": "الهيئة العامة للعقار: مؤشرات الإيجار (إيجار)",
        "en": "Real Estate General Authority (REGA): rental indicators (Ejar)",
        "license": "KSA Open Data License",
        "url": "https://open.data.gov.sa",
    },
    {
        "id": "rega_sales",
        "ar": "الهيئة العامة للعقار: مؤشرات صفقات البيع (السجل العقاري)",
        "en": "Real Estate General Authority (REGA): sales transaction indicators (Real Estate Registry)",
        "license": "KSA Open Data License",
        "url": "https://open.data.gov.sa",
    },
    {
        "id": "na_districts",
        "ar": "حدود الأحياء: العنوان الوطني عبر مستودع homaily/Saudi-Arabia-Regions-Cities-and-Districts",
        "en": "District boundaries: National Address, via homaily/Saudi-Arabia-Regions-Cities-and-Districts",
        "license": "GPL-2.0",
        "url": "https://github.com/homaily/Saudi-Arabia-Regions-Cities-and-Districts",
    },
]

MAX_PRICED_DROP = 0.05
MAX_MEDIAN_MOVE = 0.15
SIMPLIFY_DEG = 0.00015  # about 15 m, invisible at district zoom
COORD_DECIMALS = 5


def num(v, digits=0):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return round(f, digits) if digits else int(round(f))


def round_coords(obj):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(c, COORD_DECIMALS) for c in obj]
        return [round_coords(o) for o in obj]
    return obj


def reason_ar(basis, deals):
    """The confidence reason in Arabic, from the price basis and the number of deals behind it."""
    if basis == "district_sold_residential_12m":
        return f"{deals} صفقة سكنية في آخر 12 شهرًا"
    if basis == "district_sold_residential_24m":
        return f"{deals} صفقة سكنية في آخر 24 شهرًا، وأقل من 5 في آخر 12 شهرًا"
    return "صفقات قليلة جدًا لتقدير سعر موثوق"


NICE_STEPS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)


def nice_breaks(values):
    """Quintile breaks of a city's values, rounded so the legend reads cleanly.

    The rounding step comes from the city's own spread (about a tenth of the gap between the first and last
    quintile), so rents of 100 to 700 SAR/m2 round to 10 or 25, not to 250. Breaks are strictly increasing
    and every one of the five colour classes holds at least one district; when rounding would empty a
    class, a finer step is used."""
    if len(values) < 5:
        return []
    qs = statistics.quantiles(values, n=5)
    target = max((qs[-1] - qs[0]) / 10, 1)
    start = max([i for i, st in enumerate(NICE_STEPS) if st <= target], default=0)
    for step in reversed(NICE_STEPS[:start + 1]):
        out = []
        for q in qs:
            b = max(step, round(q / step) * step)
            if out and b <= out[-1]:
                b = out[-1] + step
            out.append(b)
        edges = [float("-inf")] + out + [float("inf")]
        if all(any(lo <= v < hi for v in values) for lo, hi in zip(edges, edges[1:])):
            return out
    return [round(q) for q in qs]


def rent_window(quarters):
    """"2025-Q2..2026-Q1" from the rent quarters build_rega_rent.py used, or None."""
    return f"{min(quarters)}..{max(quarters)}" if quarters else None


def read_csv(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def type_fields(did, sales, rents):
    """Per-type sale and rent fields for one district."""
    out = {}
    for t in ("land", "villa", "apartment"):
        r = sales.get((did, t))
        ppm2 = num(r["ppm2"]) if r else None
        out[f"sale_{t}"] = ppm2
        out[f"sale_{t}_n"] = num(r["deeds"]) if r else 0
        out[f"sale_{t}_conf"] = (r["confidence"] if r and ppm2 is not None else "none")
        out[f"sale_{t}_chg"] = num(r["change"], 3) if r and ppm2 is not None else None
    rr = rents.get(did, {})
    for t in RENT_TYPES:
        m2 = num(rr.get(f"rent_{t}_m2_year"))
        n = num(rr.get(f"rent_{t}_contracts")) or 0
        conf = next((c for k, c in RENT_CONF if n >= k), "none") if m2 is not None else "none"
        out[f"rent_{t}"] = m2 if conf != "none" else None
        out[f"rent_{t}_n"] = n
        out[f"rent_{t}_conf"] = conf
        out[f"rent_{t}_year"] = num(rr.get(f"rent_{t}_year")) if conf != "none" else None
    return out


RENT_BAND = 3  # a district rent per m2 outside a third to three times the city median for its type is hidden
# Ports and airport grounds have no housing; their "rents" are staff or corporate leases. Districts merely named
# after an airport or an old industrial area (Madinah's حي المطار, Riyadh's حي الصناعية) do have housing, at
# normal rents, so they stay and only the median band applies to them.
NON_RESIDENTIAL = ("ميناء", "مطار الملك")


def clean_rents(by_city):
    """Hide rent cells that are not housing.

    REGA's averages carry some corporate leases filed as a studio or apartment (a port district at 140,000
    SAR a year for a "studio"). A cell more than RENT_BAND times off its city's median per m2 for that type is
    hidden, and port and airport grounds get no rents at all."""
    hidden = defaultdict(int)
    for slug, rows in by_city.items():
        for t in RENT_TYPES:
            vals = [p[f"rent_{t}"] for p, _ in rows if p[f"rent_{t}"] is not None]
            if len(vals) < 5:
                continue
            med = statistics.median(vals)
            for p, _ in rows:
                v = p[f"rent_{t}"]
                odd = v is not None and not med / RENT_BAND <= v <= med * RENT_BAND
                if odd or (v is not None and any(w in p["name_ar"] for w in NON_RESIDENTIAL)):
                    p[f"rent_{t}"] = p[f"rent_{t}_year"] = None
                    p[f"rent_{t}_conf"] = "none"
                    hidden[slug] += 1
    if hidden:
        print("rent cells hidden (off the city median or not housing): " + ", ".join(f"{k} {v}" for k, v in hidden.items()))


def build(final_dir, base_dir):
    sales = {(r["district_id"], r["type"]): r for r in read_csv(base_dir / "sales_by_type.csv")}
    rents = {r["district_id"]: r for r in read_csv(final_dir / "rents_wide.csv")}
    windows = {}
    for r in read_csv(base_dir / "sales_by_type.csv"):
        windows[r["city"]] = r["window"]
    src = json.loads((final_dir / "price_index.geojson").read_text(encoding="utf-8"))
    features, by_city, problems = [], {c[0]: [] for c in CITIES}, []
    as_of = None
    for f in src["features"]:
        p = f["properties"]
        if p.get("level") != "district" or p.get("city") not in by_city:
            continue
        as_of = max(as_of or "", p.get("data_as_of") or "")
        ppm2 = num(p.get("sale_ppm2"))
        conf = p.get("confidence") or "none"
        if ppm2 is None:
            conf = "none"
        low, high = num(p.get("sale_ppm2_low")), num(p.get("sale_ppm2_high"))
        name_ar = (p.get("district_ar") or "").strip()
        if not name_ar:
            problems.append(f"{p['unit_id']}: no name")
        if ppm2 is not None and low is not None and low > ppm2:
            problems.append(f"{p['unit_id']}: low {low} above price {ppm2}")
        deals_basis = num(p.get("deals_basis")) or 0
        geom = shape(f["geometry"]).simplify(SIMPLIFY_DEG, preserve_topology=True)
        props = {
            "id": str(p.get("district_id") or p["unit_id"]),
            "city": p["city"],
            "name_ar": name_ar,
            "name_en": (p.get("district_en") or "").replace(" Dist.", "").strip(),
            "ppm2": ppm2,
            "low": low if ppm2 is not None else None,
            "high": high if ppm2 is not None else None,
            "conf": conf,
            "conf_score": num(p.get("confidence_score")) or 0,
            "reason_en": p.get("confidence_reason") or "",
            "reason_ar": reason_ar(p.get("price_basis"), deals_basis),
            "yoy": num(p.get("yoy_change"), 3) if ppm2 is not None else None,
            "deals_12m": num(p.get("deals_12m")) or 0,
            "value_12m": num(p.get("value_12m_sar")) or 0,
            "last_deal": p.get("last_deal") or None,
            "rent_m2": num(p.get("rent_apartment_m2_year")),
            "rent_year": num(p.get("rent_apartment_year")),
            "lng": num(p.get("lng"), 5),
            "lat": num(p.get("lat"), 5),
            **type_fields(str(p.get("district_id")), sales, rents),
        }
        features.append({"type": "Feature", "id": len(features), "properties": props,
                         "geometry": round_coords(mapping(geom))})
        by_city[p["city"]].append((props, geom))

    clean_rents(by_city)

    # Publish a city only when enough districts get a confident (high or medium) sale price for at least one
    # property type: the sale map by type is the main view, so a city with rents only would open empty.
    def confident(props):
        return any(props.get(f"{k}_conf") in ("high", "medium") for k, (mode, _) in METRICS.items() if mode == "sale")

    # ... and only when most of its registry deeds match a district polygon (otherwise the map is missing the
    # districts where most sales happen). The match rate is shown per city.
    web_meta = json.loads(WEB_META.read_text(encoding="utf-8")) if WEB_META.exists() else {}
    cov_path = base_dir / "rega_coverage.json"
    coverage = json.loads(cov_path.read_text(encoding="utf-8")) if cov_path.exists() else {}
    skipped = {}
    for slug in by_city:
        n = sum(1 for props, _ in by_city[slug] if confident(props))
        match = coverage.get(slug, {}).get("rega_match", 0)
        if by_city[slug] and (n < MIN_CONFIDENT or match < MIN_MATCH):
            skipped[slug] = f"{n} confident, {match:.0%} matched"
    if skipped:
        print(f"not published (under {MIN_CONFIDENT} confident districts or {MIN_MATCH:.0%} of deeds matched): "
              + "; ".join(f"{k} ({v})" for k, v in skipped.items()))
        features = [f for f in features if f["properties"]["city"] not in skipped]
        for i, f in enumerate(features):
            f["id"] = i
        for slug in skipped:
            by_city[slug] = []

    cities = []
    for slug, ar, en in CITIES:
        rows = by_city[slug]
        if not rows:
            continue
        prices = [r[0]["ppm2"] for r in rows if r[0]["ppm2"] is not None]
        minx = min(g.bounds[0] for _, g in rows)
        miny = min(g.bounds[1] for _, g in rows)
        maxx = max(g.bounds[2] for _, g in rows)
        maxy = max(g.bounds[3] for _, g in rows)
        cities.append({
            "slug": slug, "ar": ar, "en": en,
            "bounds": [round(minx, 4), round(miny, 4), round(maxx, 4), round(maxy, 4)],
            "districts": len(rows),
            "priced": len(prices),
            "high": sum(1 for r, _ in rows if r["conf"] == "high"),
            "median_ppm2": int(statistics.median(prices)) if prices else None,
            "breaks": nice_breaks(prices),
            "sale_window": windows.get(slug),
            "match": coverage.get(slug, {}).get("rega_match"),
            "rent_window": rent_window(web_meta.get(slug, {}).get("rent_quarters")),
            "metrics": {
                k: {
                    "breaks": nice_breaks([r[k] for r, _ in rows if r[k] is not None]),
                    "priced": sum(1 for r, _ in rows if r[k] is not None),
                    "median": int(statistics.median([r[k] for r, _ in rows if r[k] is not None]))
                    if any(r[k] is not None for r, _ in rows) else None,
                }
                for k in METRICS
            },
        })

    meta = {
        "data_as_of": as_of,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "sale_as_of": max((w.split("..")[-1] for w in windows.values()), default=None),
        "metrics": {k: {"mode": m, "type": t} for k, (m, t) in METRICS.items()},
        "cities": cities,
        "sources": SOURCES,
        "totals": {
            "districts": len(features),
            "priced": sum(c["priced"] for c in cities),
            "high": sum(c["high"] for c in cities),
        },
    }
    market = build_market(base_dir, by_city, cities)
    return {"type": "FeatureCollection", "features": features}, meta, market, problems


def build_market(base_dir, by_city, cities):
    """Home page stats per city: quarterly series per type, rents, top districts."""
    q = defaultdict(list)
    for r in read_csv(base_dir / "market_quarterly.csv"):
        q[(r["city"], r["type"])].append(r)
    out = {"cities": {}}
    for c in cities:
        slug = c["slug"]
        rows = [r for r, _ in by_city[slug]]
        types = {}
        for t in SALE_TYPES:
            series = sorted(q.get((slug, t), []), key=lambda r: r["quarter"])
            pts = []
            for r in series:
                ppm2 = num(r["ppm2"])
                prior = [p["ppm2"] for p in pts[-4:] if p["ppm2"]]
                # A city average that jumps far from the last year is a data glitch (e.g. raw land
                # deals in one quarter); keep the deal count but not the price.
                if ppm2 and len(prior) >= 2 and not 0.5 <= ppm2 / statistics.median(prior) <= 2:
                    ppm2 = None
                pts.append({"q": r["quarter"], "deeds": num(r["deeds"]) or 0,
                            "value": num(r["value"]) or 0, "ppm2": ppm2})
            if pts:
                types[t] = pts
        def top(key, n_key, by="price", k=5):
            cand = [r for r in rows if r.get(key) is not None and r.get(f"{key}_conf") in ("high", "medium")]
            cand.sort(key=lambda r: -(r[key] if by == "price" else r[n_key]))
            return [{"id": r["id"], "name_ar": r["name_ar"], "name_en": r["name_en"],
                     "value": r[key], "n": r[n_key]} for r in cand[:k]]
        out["cities"][slug] = {
            "types": types,
            "moj": {
                "deals_12m": sum(r["deals_12m"] for r in rows),
                "value_12m": sum(num(r.get("value_12m")) or 0 for r in rows),
            },
            "rent": {t: c["metrics"][f"rent_{t}"]["median"] for t in RENT_TYPES},
            "rent_year": {t: c["metrics"][f"rent_{t}_year"]["median"] for t in RENT_TYPES},
            "rent_window": c["rent_window"],
            "sale_window": c["sale_window"],
            "sale": {t: c["metrics"][f"sale_{t}"]["median"] for t in ("land", "villa", "apartment")},
            "top_price": {t: top(f"sale_{t}", f"sale_{t}_n") for t in ("land", "villa", "apartment")},
            "top_active": {t: top(f"sale_{t}", f"sale_{t}_n", by="n") for t in ("land", "villa", "apartment")},
        }
    return out


def gates(meta, previous, problems):
    """Return the list of failed checks against the last published meta.json."""
    failed = list(problems)
    if not previous:
        return failed
    prev = {c["slug"]: c for c in previous.get("cities", [])}
    for c in meta["cities"]:
        p = prev.get(c["slug"])
        if not p:
            continue
        if p["priced"] and c["priced"] < p["priced"] * (1 - MAX_PRICED_DROP):
            failed.append(f"{c['slug']}: priced districts fell from {p['priced']} to {c['priced']}")
        # Medians of small cities swing with a handful of deals, so the move check needs 30+ priced districts.
        if p.get("median_ppm2") and c.get("median_ppm2") and p["priced"] >= 30:
            move = c["median_ppm2"] / p["median_ppm2"] - 1
            if abs(move) > MAX_MEDIAN_MOVE:
                failed.append(f"{c['slug']}: median moved {move:+.0%} ({p['median_ppm2']} to {c['median_ppm2']})")
        for k, m in c.get("metrics", {}).items():
            pm = p.get("metrics", {}).get(k)
            if not pm:
                continue
            if pm["priced"] and m["priced"] < pm["priced"] * (1 - MAX_PRICED_DROP):
                failed.append(f"{c['slug']} {k}: priced districts fell from {pm['priced']} to {m['priced']}")
            if pm["priced"] >= 30 and pm.get("median") and m.get("median") and abs(m["median"] / pm["median"] - 1) > MAX_MEDIAN_MOVE:
                failed.append(f"{c['slug']} {k}: median moved {m['median'] / pm['median'] - 1:+.0%}")
    for slug in prev:
        if slug not in {c["slug"] for c in meta["cities"]}:
            failed.append(f"{slug}: city missing")
    return failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", required=True, type=Path, help="folder with price_index.geojson")
    ap.add_argument("--base", required=True, type=Path, help="folder with sales_by_type.csv, market_quarterly.csv")
    ap.add_argument("--out", required=True, type=Path, help="public data folder of the heat map")
    ap.add_argument("--force", action="store_true", help="publish even if a quality gate fails")
    args = ap.parse_args()

    geo, meta, market, problems = build(args.final, args.base)
    meta_path = args.out / "meta.json"
    previous = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None

    failed = gates(meta, previous, problems)
    for line in failed:
        print(f"GATE FAILED  {line}", file=sys.stderr)
    if failed and not args.force:
        print("Not publishing: the last good data stays live.", file=sys.stderr)
        sys.exit(1)

    if previous and previous.get("data_as_of") == meta["data_as_of"]:
        same = {k: v for k, v in previous.items() if k != "built_at"} == {k: v for k, v in meta.items() if k != "built_at"}
        if same:
            meta["built_at"] = previous["built_at"]

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "districts.geojson").write_text(
        json.dumps(geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "market.json").write_text(json.dumps(market, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for c in meta["cities"]:
        print(f"{c['slug']:8} {c['priced']:4}/{c['districts']:<4} priced, {c['high']:4} high, "
              f"median {c['median_ppm2']}; " + ", ".join(f"{k} {m['priced']}@{m['median']}" for k, m in c["metrics"].items()))
    size = (args.out / "districts.geojson").stat().st_size
    print(f"data as of {meta['data_as_of']}, districts.geojson {size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
