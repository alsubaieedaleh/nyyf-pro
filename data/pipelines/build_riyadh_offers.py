"""Build the Riyadh land offers layer (asking prices) for the map.

Reads the scraped land offers from the old nyyf (Muqayyim) repo, assigns each offer to a
district from apps/web/public/data/riyadh-districts.geojson (run build_moj_market.py first),
and writes:

  apps/web/public/data/riyadh-offers.geojson     land offers (asking prices, with the plan number
                                                 when the offer text names one)
  apps/web/public/data/riyadh-offers-text.json   offer descriptions by id, loaded on demand

Usage:
  pip install shapely
  python data/pipelines/build_riyadh_offers.py <old-repo>/Web/muqayyim/src/assets
"""

import json
import re
import sys
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "apps" / "web" / "public" / "data"

# Offers priced far from their district's sold median are usually typos or mislabelled land
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


ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
# "مخطط 3057", "مخطط رقم ٣٠٥٧", "المخطط: 3057"
PLAN_RE = re.compile(r"مخطط\s*(?:رقم)?\s*[:\-]?\s*([0-9٠-٩]{2,5})(?![0-9٠-٩])")


def plan_number(text):
    """Plan (مخطط) number written in the offer text, if any."""
    m = PLAN_RE.search(text or "")
    return m[1].translate(ARABIC_DIGITS).lstrip("0") or None if m else None


def clean_text(text, limit=160):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main(assets_dir):
    assets = Path(assets_dir)
    districts = load_features(OUT / "riyadh-districts.geojson")
    raw_offers = load_features(assets / "riyadh_landsOffers.geojson") + load_features(
        assets / "new_landsOffer.geojson"
    )

    polygons = [shape(d["geometry"]) for d in districts]
    tree = STRtree(polygons)

    seen = set()
    offers = []
    offer_texts = {}
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
            if district["ppm2"] and not (MIN_RATIO_TO_DISTRICT <= ppm2 / district["ppm2"] <= MAX_RATIO_TO_DISTRICT):
                continue
            district_id = district["id"]

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
                    "plan": plan_number(f["properties"].get("content")),
                },
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "riyadh-offers.geojson"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": offers}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{path.relative_to(ROOT)}: {len(offers)} features, {path.stat().st_size / 1e6:.1f} MB")
    with open(OUT / "riyadh-offers-text.json", "w", encoding="utf-8") as f:
        json.dump(offer_texts, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
