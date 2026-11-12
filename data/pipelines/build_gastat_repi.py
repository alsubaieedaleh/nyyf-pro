"""GASTAT Real Estate Price Index (2023 = 100) to JSON: by property type nationally and by administrative region.

This is the freshest official price signal there is (it reaches the quarter that just ended, about six weeks after it),
and unlike the MOJ open files it covers the Real Estate Registry, so it still moves for Riyadh. It has no districts
and no prices, only index values, so the map uses it as context ("Riyadh region prices +4.6% on a year"), never
to make or move a district price.

Input: the GASTAT "repi_qN_YYYY_ar-en" workbook (sheet 2: national by sector and type, sheet 3: by region), as
fetched by fetch_latest.py into <tree>/gastat/repi.xlsx.

Output (one file):
  {"source": ..., "as_of": "2026-Q3", "national": {"all": [...], "residential_plot": [...], ...},
   "regions": {"Riyadh": [...], ...}}
  each series a list of {"q": "2026-Q3", "index": 105.11, "qoq": -1.2, "yoy": 1.2} (qoq / yoy null where GASTAT
  has none).

Usage: python build_gastat_repi.py --xlsx <tree>/gastat/repi.xlsx --out apps/heatmap/public/data/repi.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import openpyxl

QUARTERS = {"الربع الأول": 1, "الربع الاول": 1, "الربع الثاني": 2, "الربع الثالث": 3, "الربع الرابع": 4}
TYPES = {  # English header in sheet 2 -> key
    "total residential": "residential", "residential plot": "residential_plot", "villa": "villa",
    "apartment": "apartment", "floor": "floor", "total commercial": "commercial", "commercial plot": "commercial_plot",
    "building": "building", "gallery/ shop": "shop", "total agricultural": "agricultural",
    "agricultural land": "agricultural_land",
}
REGIONS = {  # GASTAT English name -> the rent_region key used in cities.json
    "Riyadh": "Riyadh", "Makkah": "Makkah", "Madinah": "Madinah", "Al Qaseem": "AlQassim",
    "Eastern Province": "EP", "Aseer": "Aseer", "Tabouk": "Tabuk", "Hail": "Hail", "Northern Borders": "NB",
    "Jazan": "Jazan", "Najran": "Najran", "Al Baha": "AlBaha", "Al Jouf": "AlJawf",
}


def val(v):
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    return None


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def series(ws, header_row: int, names: dict) -> dict:
    """Read a sheet whose header_row names a block of three columns (index, QoQ, YoY) per series, starting after the
    general index (columns C-E)."""
    header = [c.value for c in ws[header_row]]
    starts = {}
    for i, h in enumerate(header):
        key = names.get(norm(h)) or names.get(str(h or "").strip())
        if key:
            starts[key] = i
    starts["all"] = 2  # the general index
    out = {k: [] for k in starts}
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        year, qname = row[0], str(row[1] or "").strip()
        if not isinstance(year, int) or qname not in QUARTERS:
            continue  # notes, blank rows and annual averages
        q = f"{year}-Q{QUARTERS[qname]}"
        for k, i in starts.items():
            if val(row[i]) is None:
                continue
            out[k].append({"q": q, "index": val(row[i]), "qoq": val(row[i + 1]), "yoy": val(row[i + 2])})
    return out


def find_row(ws, needle: str) -> int:
    for r in ws.iter_rows():
        if any(needle in norm(c.value) for c in r):
            return r[0].row
    raise SystemExit(f"{ws.title}: no header row with {needle!r}; the GASTAT layout changed")


def build(xlsx: Path) -> dict:
    wb = openpyxl.load_workbook(xlsx, data_only=True, read_only=False)
    by_type = wb["2"]
    by_region = wb["3"]
    national = series(by_type, find_row(by_type, "residential plot"), TYPES)
    regions = series(by_region, find_row(by_region, "eastern province"), {norm(k): v for k, v in REGIONS.items()})
    regions.pop("all", None)
    as_of = max(p["q"] for p in national["all"])
    for name, s in {**national, **regions}.items():
        if not s or s[-1]["q"] != as_of:
            raise SystemExit(f"GASTAT series {name} does not reach {as_of}")
    return {
        "source": "General Authority for Statistics (GASTAT), Real Estate Price Index, 2023 = 100",
        "as_of": as_of,
        "national": national,
        "regions": regions,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    data = build(args.xlsx)
    args.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    last = {k: v[-1] for k, v in data["regions"].items()}
    print(f"GASTAT price index to {data['as_of']}: national {data['national']['all'][-1]}")
    for k, p in last.items():
        print(f"  {k}: index {p['index']}, QoQ {p['qoq']}%, YoY {p['yoy']}%")


if __name__ == "__main__":
    main()
