"""Build the Riyadh seed datasets for the map prototype.

Reads the GeoJSON files from the old nyyf (Muqayyim) repo and writes small,
clean files for the web app:

  apps/web/public/data/riyadh-districts.geojson  district polygons + stats
  apps/web/public/data/riyadh-offers.geojson     land offers (asking prices)
  apps/web/public/data/riyadh-offers-text.json   offer descriptions by id, loaded on demand

Usage:
  pip install shapely
  python data/pipelines/build_riyadh_seed.py <old-repo>/Web/muqayyim/src/assets
"""

import json
import re
import statistics
import sys
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "apps" / "web" / "public" / "data"

# A district needs this many offers before its asking median is shown.
MIN_OFFERS_FOR_STATS = 3

# Offers priced far from their district average are usually typos or mislabelled land
# (farms listed inside the city); they are dropped rather than shown as bargains.
MIN_RATIO_TO_DISTRICT = 0.3
MAX_RATIO_TO_DISTRICT = 4

# Offers outside these bounds are treated as data-entry mistakes.
MIN_AREA_M2 = 100
MAX_AREA_M2 = 5_000_000
MIN_PPM2 = 50
MAX_PPM2 = 50_000


def load_features(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["features"]


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_text(text, limit=160):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main(assets_dir):
    assets = Path(assets_dir)
    districts = load_features(assets / "riyadh_districts.geojson")
    raw_offers = load_features(assets / "riyadh_landsOffers.geojson") + load_features(
        assets / "new_landsOffer.geojson"
    )

    polygons = [shape(d["geometry"]) for d in districts]
    tree = STRtree(polygons)

    seen = set()
    offers = []
    offer_texts = {}
    asking_by_district = {}
    for f in raw_offers:
        lng, lat = f["geometry"]["coordinates"][:2]
        price = to_float(f["properties"].get("price"))
        area = to_float(f["properties"].get("area"))
        # The two source files overlap with slightly shifted coordinates, so match within ~100 m.
        key = (round(lng, 3), round(lat, 3), price, area)
        if key in seen or not price or not area:
            continue
        seen.add(key)
        if not (MIN_AREA_M2 <= area <= MAX_AREA_M2):
            continue
        ppm2 = price / area
        if not (MIN_PPM2 <= ppm2 <= MAX_PPM2):
            continue

        point = Point(lng, lat)
        district_idx = next(
            (int(i) for i in tree.query(point) if polygons[int(i)].contains(point)), None
        )
        district_id = None
        if district_idx is not None:
            district = districts[district_idx]["properties"]
            ratio = ppm2 / district["average_price_per_meter"]
            if not (MIN_RATIO_TO_DISTRICT <= ratio <= MAX_RATIO_TO_DISTRICT):
                continue
            district_id = district["district_id"]
        if district_id is not None:
            asking_by_district.setdefault(district_id, []).append(ppm2)

        offer_texts[len(offers) + 1] = clean_text(f["properties"].get("content"))
        offers.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lng, 5), round(lat, 5)]},
                "properties": {
                    "id": len(offers) + 1,
                    "price": round(price),
                    "area": round(area),
                    "ppm2": round(ppm2),
                    "district_id": district_id,
                },
            }
        )

    district_out = []
    for d, poly in zip(districts, polygons):
        p = d["properties"]
        asking = asking_by_district.get(p["district_id"], [])
        asking_ppm2 = round(statistics.median(asking)) if len(asking) >= MIN_OFFERS_FOR_STATS else None
        ppm2 = round(p["average_price_per_meter"])
        district_out.append(
            {
                "type": "Feature",
                "id": p["district_id"],
                "geometry": json.loads(json.dumps(poly.simplify(0.0002).__geo_interface__)),
                "properties": {
                    "id": p["district_id"],
                    "name_ar": p["الحي"],
                    "name_en": p["name_en"],
                    "ppm2": ppm2,
                    "offers": len(asking),
                    "asking_ppm2": asking_ppm2,
                    "gap": round((asking_ppm2 - ppm2) / ppm2, 3) if asking_ppm2 else None,
                },
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    for name, features in (("riyadh-districts", district_out), ("riyadh-offers", offers)):
        path = OUT / f"{name}.geojson"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{path.relative_to(ROOT)}: {len(features)} features, {path.stat().st_size / 1e6:.1f} MB")
    with open(OUT / "riyadh-offers-text.json", "w", encoding="utf-8") as f:
        json.dump(offer_texts, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
