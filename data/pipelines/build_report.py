"""Quarterly district report for the market page and the report email.

For each published city, as of its latest quarter with district data, it ranks districts by how their price
per m2 moved against the same quarter a year earlier, counts streaks (quarters in a row on the same side of
last year), and lists the busiest districts. It writes report.json.

Each city uses the source that describes it best:

  * "rega": REGA sales indicators (Real Estate Registry deeds) by district, property type and quarter.
    Split by type (land, villa, apartment), price = total value / total area. Used when the registry
    district files are recent (within 2 quarters of MOJ), or when MOJ no longer records most of the city's
    sales (Riyadh moved most transfers to the Real Estate Registry in 2025).
  * "moj": MOJ open deals, median price per m2 of single-property residential sales, bulk batches left out.
    Land, villas and apartments together (MOJ stopped recording the type after 2023-Q3). Used where the
    registry district files are old and MOJ still records the city's usual volume.

A comparison needs MIN_DEEDS (registry) or MIN_DEALS (MOJ) on both sides; quarters missing from a source
(for example MOJ 2025-Q2, see build_moj_market.py) are skipped rather than counted as a break in a streak.
A window holding a bulk quarter (3x the district's usual volume) is not compared. The headline lists (top
risers, fallers, streaks) only take districts with HEADLINE_MIN deeds on both sides and a move within
HEADLINE_MAX; larger moves count in the totals and the median and are reported as "wide".
The registry files are district totals (value and area), so a median per deed is not possible there.

Usage:
  python build_report.py --deals <final>/deals_clean.csv.gz --rega <base>/sales_district_quarterly.csv \
      --districts <public>/districts.geojson --out <public>/report.json
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cities import CITY_LIST  # noqa: E402

WINDOW = 2  # quarters in each price window: the latest half-year against the same half-year a year earlier
MIN_DEEDS = 20  # registry deeds per district and type in each window
MIN_DEALS = 20  # MOJ priced deals per district in each window
# A move beyond this in a year almost always means a different mix (one large raw-land deed, a new project),
# not a district repricing, so such comparisons are counted as "excluded" instead of ranked.
MAX_MOVE = 0.75
MAX_COUNT_RATIO = 3  # the two windows' deal counts must be within this factor
MIN_MOJ_MATCH = 0.6  # share of a city's MOJ deals matched to a district before MOJ can be its source
MAX_GAP = 2  # quarters the registry may lag MOJ and still be the source
MIN_COVERAGE = 0.75  # below this share of its usual volume, MOJ is not a fair sample of a city
# Pick: the preferred source when it compares 15+ districts, else the one that compares the most (5+ needed).
TOP = 8
# The headline lists (top risers, fallers, streaks) are what a broker reads first, so they hold a stricter bar:
# 50+ deeds or deals on both sides and a move within +-40%. Bigger moves still count in the totals and the
# median, and are counted as "wide" with a note that they usually mean a different mix of what sold.
HEADLINE_MIN = 50
HEADLINE_MAX = 0.40
# A quarter with 3x the district's usual volume (median of the 4 quarters before, 30+ deeds) is a bulk event:
# a new plan opening, a government programme handover (such as the capped 1,500 SAR/m2 plots in north Riyadh),
# or a developer batch. Its price is not the district's market price, so a window holding one is not compared.
SPIKE_RATIO = 3
SPIKE_MIN = 30
SEGMENTS = {"rega": ["land", "villa", "apartment"], "moj": ["all"]}


def qnum(q: str) -> int:
    return int(q[:4]) * 4 + int(q[-1]) - 1


def qstr(n: int) -> str:
    return f"{n // 4}-Q{n % 4 + 1}"


def load_moj(path: Path):
    """city -> district -> quarter -> [ppm2]; city -> quarter -> deal count."""
    prices = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    volume = defaultdict(lambda: defaultdict(int))
    matched = defaultdict(lambda: defaultdict(int))
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["class"] != "residential":
                continue
            volume[r["city"]][r["quarter"]] += 1
            matched[r["city"]][r["quarter"]] += r["geo_level"] != "city"
            if r["geo_level"] == "district" and r["district_id"] and r["ppm2_usable"] == "True" and r["ppm2"]:
                prices[r["city"]][r["district_id"]][r["quarter"]].append(float(r["ppm2"]))
    return prices, volume, matched


def load_rega(path: Path):
    """city -> type -> district -> quarter -> (ppm2, deeds)."""
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ppm2"]:
                out[r["city"]][r["type"]][r["district_id"]][r["quarter"]] = (float(r["value"]), float(r["area"]), int(r["deeds"]))
    return out


def coverage(volume: dict) -> float:
    """Deals a quarter in the last 4 quarters with data against the 4 before."""
    qs = sorted(volume, key=qnum)
    if not qs:
        return 0.0
    last = qnum(qs[-1])
    now = [volume[q] for q in qs if qnum(q) > last - 4]
    before = [volume[q] for q in qs if last - 8 < qnum(q) <= last - 4]
    return (sum(now) / len(now)) / (sum(before) / len(before)) if now and before else 1.0


def complete_quarter(volume: dict) -> str | None:
    """Latest quarter whose volume is not cut short (registration lag in the newest file)."""
    qs = sorted(volume, key=qnum)
    for q in reversed(qs):
        prior = [volume[p] for p in qs if qnum(q) - 4 <= qnum(p) < qnum(q)]
        if not prior or volume[q] >= 0.5 * statistics.median(prior):
            return q
    return qs[-1] if qs else None


def full_windows(latest: str | None, have: set) -> str | None:
    """The newest quarter, at or before latest, whose window and year-earlier window are both fully in the source.

    A quarter the source lacks (MOJ 2025-Q2 was never republished correctly) would make one side of the comparison
    shorter than the other and the label wrong, so the report steps back to the newest pair of whole windows."""
    if not latest:
        return None
    n = qnum(latest)
    for m in range(n, n - 5, -1):
        need = set(range(m - WINDOW + 1, m + 1)) | set(range(m - 4 - WINDOW + 1, m - 4 + 1))
        if all(qstr(k) in have for k in need):
            if m != n:
                print(f"  report window stepped back from {latest} to {qstr(m)}: a quarter is missing in between")
            return qstr(m)
    return latest


def agg(qs: dict, end: int):
    """Price and count over the WINDOW quarters ending at quarter number end.

    Registry cells are (value, area, deeds): price = total value / total area. MOJ cells are lists of
    single-deal prices: price = median."""
    cells = [qs[qstr(n)] for n in range(end - WINDOW + 1, end + 1) if qstr(n) in qs]
    if not cells:
        return None
    if isinstance(cells[0], tuple):
        v, a, n = (sum(c[i] for c in cells) for i in range(3))
        return (v / a, n) if a > 0 else None
    vals = [x for c in cells for x in c]
    return statistics.median(vals), len(vals)


def count(cell) -> int:
    return cell[2] if isinstance(cell, tuple) else len(cell)


def spikes(qs: dict) -> set:
    """Quarter numbers whose volume is SPIKE_RATIO times the median of the 4 quarters before."""
    out = set()
    for q, cell in qs.items():
        n = qnum(q)
        prior = [count(qs[qstr(m)]) for m in range(n - 4, n) if qstr(m) in qs]
        if len(prior) >= 2 and count(cell) >= SPIKE_MIN and count(cell) >= SPIKE_RATIO * statistics.median(prior):
            out.add(n)
    return out


def rank(series: dict, latest: str, have: set, min_n: int, names: dict):
    """series: district -> quarter -> cell. have: quarters the source has for this city."""
    L = qnum(latest)
    rows, excluded, bulk = [], [], []
    for did, qs in series.items():
        spiked = spikes(qs)

        def yoy(n):
            a, b = agg(qs, n), agg(qs, n - 4)
            if not a or not b or a[1] < min_n or b[1] < min_n:
                return None
            window = set(range(n - WINDOW + 1, n + 1)) | set(range(n - 4 - WINDOW + 1, n - 4 + 1))
            if window & spiked:
                return "bulk"
            if max(a[1], b[1]) > MAX_COUNT_RATIO * min(a[1], b[1]):
                return None  # deal count changed so much that the mix, not the price, moved
            return a[0] / b[0] - 1

        chg = yoy(L)
        if chg is None:
            continue
        if chg == "bulk":
            bulk.append(did)
            continue
        if abs(chg) > MAX_MOVE:
            excluded.append(did)
            continue
        streak, n = 1, L - 1
        while n >= L - 12:
            if qstr(n) not in have or qstr(n - 4) not in have:
                n -= 1  # the source has no file for this quarter: skip, do not break
                continue
            c = yoy(n)
            if c is None or c == "bulk" or abs(c) > MAX_MOVE or (c > 0) != (chg > 0):
                break
            streak += 1
            n -= 1
        now, before = agg(qs, L), agg(qs, L - 4)
        nm = names.get(did, {})
        rows.append({
            "id": did,
            "name_ar": nm.get("name_ar", did),
            "name_en": nm.get("name_en", ""),
            "ppm2": int(round(now[0])),
            "ppm2_prev_year": int(round(before[0])),
            "chg": round(chg, 4),
            "streak": streak,
            "n": now[1],
            "n_prev_year": before[1],
        })
    # Busiest districts need not have a price comparison.
    active = []
    for did, qs in series.items():
        now = agg(qs, L)
        if now:
            before = agg(qs, L - 4)
            nm = names.get(did, {})
            active.append({
                "id": did, "name_ar": nm.get("name_ar", did), "name_en": nm.get("name_en", ""),
                "n": now[1], "n_chg": round(now[1] / before[1] - 1, 4) if before and before[1] else None,
                "ppm2": int(round(now[0])),
            })
    head = [r for r in rows if min(r["n"], r["n_prev_year"]) >= HEADLINE_MIN and abs(r["chg"]) <= HEADLINE_MAX]
    up = sorted([r for r in head if r["chg"] > 0], key=lambda r: -r["chg"])
    down = sorted([r for r in head if r["chg"] < 0], key=lambda r: r["chg"])
    return {
        "compared": len(rows),
        "excluded": len(excluded),
        "bulk": len(bulk),
        "wide": sum(1 for r in rows if abs(r["chg"]) > HEADLINE_MAX),
        "headline": len(head),
        "rising": sum(1 for r in rows if r["chg"] > 0),
        "falling": sum(1 for r in rows if r["chg"] < 0),
        "median_chg": round(statistics.median([r["chg"] for r in rows]), 4) if rows else None,
        "risers": up[:TOP],
        "fallers": down[:TOP],
        "streaks": sorted([r for r in head if r["chg"] > 0], key=lambda r: (-r["streak"], -r["chg"]))[:TOP],
        "active": sorted(active, key=lambda r: -r["n"])[:TOP],
    }


def insights(segments: dict):
    out = []
    for seg, s in segments.items():
        if s["risers"]:
            out.append({"kind": "top_riser", "seg": seg, "district": s["risers"][0]})
        long = s["streaks"][0] if s["streaks"] else None
        if long and long["streak"] >= 2 and (not s["risers"] or long["id"] != s["risers"][0]["id"]):
            out.append({"kind": "longest_streak", "seg": seg, "district": long})
        if s["fallers"]:
            out.append({"kind": "top_faller", "seg": seg, "district": s["fallers"][0]})
        if s["compared"]:
            out.append({"kind": "breadth", "seg": seg, "rising": s["rising"], "falling": s["falling"],
                        "total": s["compared"], "median_chg": s["median_chg"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deals", required=True, type=Path, help="deals_clean.csv.gz from build_final.py")
    ap.add_argument("--rega", required=True, type=Path, help="sales_district_quarterly.csv from build_rega_sales.py")
    ap.add_argument("--districts", required=True, type=Path, help="published districts.geojson (names, cities)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    geo = json.loads(args.districts.read_text(encoding="utf-8"))
    names = {f["properties"]["id"]: f["properties"] for f in geo["features"]}
    published = {f["properties"]["city"] for f in geo["features"]}
    moj, volume, matched = load_moj(args.deals)
    rega = load_rega(args.rega)

    cities = {}
    for c in CITY_LIST:
        slug = c["slug"]
        if slug not in published:
            continue
        moj_q = full_windows(complete_quarter(volume.get(slug, {})), set(volume.get(slug, {})))
        cov = coverage(volume.get(slug, {}))
        rega_qs = {q for t in rega.get(slug, {}).values() for qs in t.values() for q in qs}
        rega_q = max(rega_qs, key=qnum) if rega_qs else None
        candidates = []
        if rega_q:
            rega_ok = cov < MIN_COVERAGE or not moj_q or qnum(moj_q) - qnum(rega_q) <= MAX_GAP
            candidates.append(("rega", rega_q, rega_ok))
        recent = [q for q in volume.get(slug, {}) if moj_q and qnum(moj_q) - 4 < qnum(q) <= qnum(moj_q)]
        moj_match = sum(matched[slug][q] for q in recent) / max(1, sum(volume[slug][q] for q in recent))
        if moj_q and moj_match >= MIN_MOJ_MATCH:
            candidates.append(("moj", moj_q, cov >= MIN_COVERAGE))
        built = []
        for source, latest, preferred in candidates:
            if source == "rega":
                segs = {t: rank(rega[slug].get(t, {}), latest, rega_qs, MIN_DEEDS, names) for t in SEGMENTS["rega"]}
            else:
                segs = {"all": rank(moj.get(slug, {}), latest, set(volume[slug]), MIN_DEALS, names)}
            built.append((preferred, sum(s["compared"] for s in segs.values()), source, latest, segs))
        # The preferred source when it compares 15+ districts, otherwise whichever compares the most (5+).
        best = next((b for b in built if b[0] and b[1] >= 15), None) or max(built, key=lambda b: b[1], default=None)
        best = best[2:] if best and best[1] >= 5 else None
        if not best:
            print(f"{slug}: no source with 5+ district comparisons, left out of the report")
            continue
        source, latest, segs = best
        segs = {k: v for k, v in segs.items() if v["compared"] or v["active"]}
        cities[slug] = {
            "name_ar": c["ar"],
            "name_en": c["en"],
            "source": source,
            "quarter": latest,
            "from": qstr(qnum(latest) - WINDOW + 1),
            "vs": qstr(qnum(latest) - 4),
            "vs_from": qstr(qnum(latest) - 4 - WINDOW + 1),
            "moj_coverage": round(cov, 2),
            "segments": segs,
            "insights": insights(segs),
        }
        print(f"{slug:9} {source:4} {latest}  " + "  ".join(
            f"{k}: {v['compared']} compared, +{v['rising']}/-{v['falling']}" for k, v in segs.items()))

    out = {
        "period": "quarter",
        "window_quarters": WINDOW,
        "max_move": MAX_MOVE,
        "min_deeds": MIN_DEEDS,
        "min_deals": MIN_DEALS,
        "headline_min": HEADLINE_MIN,
        "headline_max": HEADLINE_MAX,
        "cities": cities,
    }
    args.out.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
