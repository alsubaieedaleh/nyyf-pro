"""Build the final Nyyf Pro dataset: one price table at the most precise level each source allows.

Reads only the base dataset (built by build_base.py), so it reruns without the source mirrors.
Each row of the price index is a location unit: a plan (مخطط) when MOJ named it and gave enough
land deals, otherwise a district. Every row says how its price was made, what it rests on and how
far to trust it.

Writes to --out:
  price_index.csv          one row per plan or district with price, range, rent, confidence, sources
  deals_clean.csv.gz       every MOJ deal with location level, outlier flag and usable price per m²
  rents_wide.csv           rent per district, one column per property type
  sources.csv              source registry: what each source gives, license, cadence, status
  coverage.csv             counts per city and level
  price_index.geojson      district polygons and placed plan points with the price index fields
  nyyf_final.xlsx          all of the above (except deals) plus the data dictionary, one sheet each

Usage:
  python data/pipelines/build_final.py --base <base-data dir> --out <base-data dir>/final
"""

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent))
from cities import CITY_AR  # noqa: E402

import numpy as np
import pandas as pd

LAND = "قطعة أرض"
# AS_OF and the 12- and 24-month windows are set in main() from the latest deal in the data.
AS_OF = date(2026, 3, 31)
WINDOW_12M = WINDOW_24M = (None, None)
PLAN_QUARTER = "2023-Q1"
MAX_RATIO = 5  # same outlier rule as build_moj_market.py
MIN_DEALS = 5  # district price needs this many deals (as on the map)
MIN_PLAN_DEALS = 3  # plan price needs this many land deals (as in build_plans.py)
GROWTH_RANGE = (0.6, 2.5)

SOURCES = [
    # id, name, gives, level, license, cadence, status, used_for
    ("moj_deals", "Ministry of Justice real estate deals (open data)",
     "Sold deals: date, district, area, price; plan and parcel only in 2023-Q1", "district (plan in 2023-Q1)",
     "KSA Open Data License, attribute \"Ministry of Justice\"", "quarterly", "active (to 2026-03-31)",
     "sold price per m², range, YoY, deal counts, plan land prices"),
    ("rega_rent", "REGA rental indicators (Ejar contracts)", "Rent per district and property type",
     "district", "KSA Open Data License, attribute \"REGA\"", "quarterly", "active (2025-Q2 to 2026-Q1)",
     "rent columns"),
    ("na_districts", "National Address district polygons (homaily mirror)", "District boundaries and names AR/EN",
     "district", "GPL-2.0 repository, clear before commercial launch", "rarely", "active",
     "district ids, names, polygons, centre points"),
    ("old_offers", "Old nyyf land offers (Riyadh)", "Asking prices with location and plan number in text",
     "point", "Analysis and prototype only, not for republishing", "none (frozen)", "active (frozen)",
     "asking price, ask/sold ratio, plan map points"),
    ("aqarsas", "Aqarsas API", "MOJ and Real Estate Registry deals by plan and parcel, coordinates add-on",
     "parcel", "Paid API plan", "daily or weekly", "pending (request sent, client ready)",
     "current plan prices; replaces the 2023-Q1 carry-forward"),
    ("moj_request", "MOJ data request (plan and parcel fields)", "Per-deal plan and parcel for every quarter",
     "plan / parcel", "Official agreement", "quarterly", "pending (request drafted)",
     "current plan prices from the official source"),
    ("momah_gis", "MOMAH / Balady GIS layers", "Plan and parcel polygons with numbers",
     "plan / parcel", "Data-sharing agreement", "monthly", "pending (request drafted)",
     "plan polygons on the map, placing every plan"),
    ("broker_deals", "Broker-submitted deals and listings (Nyyf Pro users)", "Closed prices and asking prices with exact location",
     "parcel / point", "Users' own data under Nyyf terms", "live", "planned (Phase 2)",
     "fresh asking and sold prices, Riyadh registry gap"),
]


def trimmed(values):
    """Values within MAX_RATIO of their median (the outlier rule used across the pipelines)."""
    v = np.asarray([x for x in values if pd.notna(x)], dtype=float)
    if len(v) == 0:
        return v
    m = np.median(v)
    return v[(v / m >= 1 / MAX_RATIO) & (v / m <= MAX_RATIO)]


def stats(values):
    v = trimmed(values)
    if len(v) == 0:
        return pd.Series({"n": 0, "p25": np.nan, "med": np.nan, "p75": np.nan})
    return pd.Series({"n": len(v), "p25": np.percentile(v, 25), "med": np.median(v), "p75": np.percentile(v, 75)})


def band(price, s):
    """25th to 75th percentile range around a headline price, as the deals' spread around their median.

    The headline comes from the base tables (the same numbers the map shows); the spread is
    recomputed here, so it is applied as a ratio to keep the range around the headline."""
    if s is None or not s["n"] or pd.isna(s["med"]):
        return np.nan, np.nan
    return price * s["p25"] / s["med"], price * s["p75"] / s["med"]


def confidence(n, spread, months_old, method_cap):
    """Score 0-100 from deal count, price spread (IQR / median) and data age; then a label.

    method_cap limits the label for estimates that are not direct current sales."""
    if not n or pd.isna(n):
        return 0, "none"
    if pd.notna(spread) and spread < 0.02:
        spread = 1.5  # a zero-width range means one repeated price (a bulk batch), not agreement
    score = min(50, 50 * np.log10(n) / np.log10(100))  # 100+ deals = full marks
    score += 30 * max(0.0, 1 - min(spread if pd.notna(spread) else 1.5, 1.5) / 1.5)
    score += 20 * max(0.0, 1 - months_old / 36)
    score = round(min(score, method_cap))
    label = "high" if score >= 70 else "medium" if score >= 45 else "low"
    return score, label


def r(x, nd=0):
    return round(float(x), nd) if pd.notna(x) else np.nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    base, out = args.base, args.out
    out.mkdir(parents=True, exist_ok=True)

    deals = pd.read_csv(base / "deals.csv.gz", dtype={"plan": str, "parcel": str, "type": str, "ref": str},
                        parse_dates=["date"], low_memory=False)
    districts = pd.read_csv(base / "districts.csv")
    plans = pd.read_csv(base / "plans.csv", dtype={"plan": str})
    rents = pd.read_csv(base / "rents.csv")
    offers = pd.read_csv(base / "offers.csv", dtype={"plan": str})
    geo = json.loads((base / "districts.geojson").read_text(encoding="utf-8"))

    global AS_OF, WINDOW_12M, WINDOW_24M
    last = deals["date"].max()
    AS_OF = last.date()
    WINDOW_12M = (last - pd.DateOffset(years=1) + pd.Timedelta(days=1), last)
    WINDOW_24M = (last - pd.DateOffset(years=2) + pd.Timedelta(days=1), last)

    # MOJ coverage per city: deals a quarter in the last 12 months against the 12 months before (quarters with
    # data only, so a missing file does not count as a fall). Riyadh moved most transfers to the Real Estate
    # Registry in 2025, so its remaining MOJ deals are not a fair sample and its MOJ prices are capped.
    dq = deals.groupby(["city", "quarter"]).size()
    coverage = {}
    for city in deals["city"].unique():
        qs = dq[city]
        now = [qs[q] for q in qs.index if pd.Period(q, "Q").end_time >= WINDOW_12M[0]]
        before = [qs[q] for q in qs.index if WINDOW_24M[0] <= pd.Period(q, "Q").end_time < WINDOW_12M[0]]
        coverage[city] = (np.mean(now) / np.mean(before)) if now and before else 1.0
    print("MOJ coverage (deals a quarter, last 12 months vs the 12 before):",
          ", ".join(f"{c} {v:.0%}" for c, v in sorted(coverage.items(), key=lambda kv: kv[1])))

    def coverage_cap(city):
        v = coverage.get(city, 1.0)
        return 44 if v < 0.5 else 69 if v < 0.75 else 100

    # ---- Clean deals: location level, outlier flag, usable price per m² ----
    deals["district_id"] = deals["district_id"].astype("Int64")
    deals["geo_level"] = np.where(deals["district_id"].isna(), "city",
                                  np.where(deals["plan"].notna(), "plan", "district"))
    deals["is_land"] = deals["type"].eq(LAND)
    grp_med = deals.groupby(["district_id", "class"])["ppm2"].transform("median")
    ratio = deals["ppm2"] / grp_med
    deals["outlier"] = deals["ppm2"].notna() & ((ratio > MAX_RATIO) | (ratio < 1 / MAX_RATIO))
    deals["ppm2_usable"] = deals["ppm2"].notna() & ~deals["outlier"] & deals["properties"].eq(1)
    deals["source"] = "moj_deals"
    deals_out = deals[["ref", "date", "quarter", "city", "district_raw", "district_id", "plan", "parcel", "geo_level",
                       "class", "type", "is_land", "properties", "price", "area_m2", "ppm2", "outlier", "ppm2_usable",
                       "source"]].copy()
    deals_out["date"] = deals_out["date"].dt.date
    deals_out.to_csv(out / "deals_clean.csv.gz", index=False, compression="gzip")

    res = deals[deals["class"].eq("residential") & deals["district_id"].notna() & deals["properties"].eq(1)]
    in12 = res[res["date"].between(*WINDOW_12M)]
    d12 = in12.groupby("district_id")["ppm2"].apply(stats).unstack()
    d24 = res[res["date"].between(*WINDOW_24M)].groupby("district_id")["ppm2"].apply(stats).unstack()

    # District land price carried to today, so district rows compare with plan rows.
    q1 = res[res["quarter"].eq(PLAN_QUARTER)]
    land_q1 = q1[q1["is_land"]].groupby("district_id")["ppm2"].apply(stats).unstack()
    res_q1 = q1.groupby("district_id")["ppm2"].apply(lambda v: np.median(trimmed(v)) if len(trimmed(v)) >= MIN_DEALS else np.nan)

    # ---- Rents, wide ----
    rw = rents.pivot_table(index="district_id", columns="type", values=["rent_year", "rent_m2_year", "contracts"])
    rw.columns = [f"rent_{t}_{'contracts' if v == 'contracts' else 'm2_year' if v == 'rent_m2_year' else 'year'}"
                  for v, t in rw.columns]
    rw = rw.reset_index()
    rent_contracts = rents.groupby("district_id")["contracts"].sum()

    # ---- Asking prices per district and plan (Riyadh offers) ----
    off_d = offers.dropna(subset=["district_id"]).groupby("district_id")["ppm2"].apply(stats).unstack()

    # ---- Plan land price spread from 2023-Q1 land deals ----
    # (any class: build_plans.py counts every land deal in the plan, not only residential ones)
    pl = deals[deals["quarter"].eq(PLAN_QUARTER) & deals["is_land"] & deals["plan"].notna() & deals["properties"].eq(1)]
    pq = pl.groupby(["district_id", "plan"])["ppm2"].apply(stats).unstack()

    # Age of the middle of the 12-month window at build time, so confidence falls as the data gets older.
    months_old_12m = max(6, (date.today() - (AS_OF - pd.Timedelta(days=182).to_pytimedelta())).days / 30.4)
    months_old_q1 = (AS_OF.year - 2023) * 12 + AS_OF.month - 2  # mid 2023-Q1 to as-of

    rows = []
    dist_info = {}
    for d in districts.itertuples():
        did = d.district_id
        s = d12.loc[did] if did in d12.index else None
        n12 = int(s["n"]) if s is not None else 0
        growth = np.nan
        if pd.notna(d.ppm2_12m) and did in res_q1.index and pd.notna(res_q1[did]):
            growth = float(np.clip(d.ppm2_12m / res_q1[did], *GROWTH_RANGE))
        land = land_q1.loc[did] if did in land_q1.index else None
        land_now = land["med"] * growth if land is not None and land["n"] >= MIN_PLAN_DEALS and pd.notna(growth) else np.nan

        if pd.notna(d.ppm2_12m):
            price = d.ppm2_12m
            lo, hi = band(price, s)
            basis, n_basis = "district_sold_residential_12m", n12
            score, label = confidence(n12, (hi - lo) / price, months_old_12m, coverage_cap(d.city))
        elif did in d24.index and d24.loc[did, "n"] >= MIN_DEALS:
            # Too few sales in 12 months: widen to 24 months, unadjusted for the change in between.
            s24 = d24.loc[did]
            price = s24["med"]
            lo, hi = band(price, s24)
            basis, n_basis = "district_sold_residential_24m", int(s24["n"])
            score, label = confidence(n_basis, (hi - lo) / price, months_old_12m + 6, min(50, coverage_cap(d.city)))
        else:
            price = lo = hi = np.nan
            basis, n_basis, score, label = "no_price", 0, 0, "none"

        o = off_d.loc[did] if did in off_d.index else None
        ask = o["med"] if o is not None and o["n"] >= 3 else np.nan
        srcs = ["moj_deals" if basis != "no_price" else None, "rega_rent" if did in rent_contracts.index else None,
                "old_offers" if pd.notna(ask) else None, "na_districts"]
        reason = {
            "district_sold_residential_12m": f"{n12} residential sales in the last 12 months"
            + (f"; MOJ now records only {coverage[d.city]:.0%} of this city's usual volume" if coverage_cap(d.city) < 100 else ""),
            "district_sold_residential_24m": f"{n_basis} residential sales in 24 months; under {MIN_DEALS} in the last 12",
            "no_price": "under 5 residential sales in 24 months; use a neighbouring district",
        }[basis]
        dist_info[did] = {"name_ar": d.name_ar, "name_en": d.name_en, "ppm2_12m": d.ppm2_12m, "growth": growth,
                          "lng": d.lng, "lat": d.lat, "rent_apt": d.rent_apt_year,
                          "yoy": r(d.yoy, 3), "last_deal": d.last_deal if pd.notna(d.last_deal) else ""}
        rows.append({
            "unit_id": f"{d.city}:{did}", "level": "district", "city": d.city, "city_ar": CITY_AR[d.city],
            "district_id": did, "district_ar": d.name_ar, "district_en": d.name_en, "plan_no": "",
            "sale_ppm2": r(price), "sale_ppm2_low": r(lo), "sale_ppm2_high": r(hi), "price_basis": basis,
            "deals_basis": n_basis, "land_ppm2_est": r(land_now), "district_ppm2_12m": r(d.ppm2_12m),
            "district_growth_since_2023q1": r(growth, 2), "yoy_change": r(d.yoy, 3), "deals_12m": d.deals_12m,
            "value_12m_sar": d.value_12m, "deals_total": d.deals_total, "last_deal": d.last_deal if pd.notna(d.last_deal) else "",
            "asking_ppm2": r(ask), "offers": int(o["n"]) if o is not None else 0,
            "ask_to_sold": r(ask / price, 2) if pd.notna(ask) and pd.notna(price) else np.nan,
            "rent_apartment_year": d.rent_apt_year, "rent_apartment_m2_year": d.rent_apt_m2_year,
            "rent_contracts": int(rent_contracts.get(did, 0)),
            "lng": d.lng, "lat": d.lat, "geo_precision": "district_centroid",
            "confidence": label, "confidence_score": score, "confidence_reason": reason,
            "sources": ";".join(s for s in srcs if s), "data_as_of": AS_OF.isoformat(),
        })

    for p in plans.itertuples():
        di = dist_info.get(p.district_id, {})
        k = (p.district_id, p.plan)
        s = pq.loc[k] if k in pq.index else None
        growth = p.district_growth
        if pd.notna(p.ppm2_est_now):
            price = p.ppm2_est_now
            lo, hi = band(price, s)
            basis = "plan_land_2023q1_x_district_growth"
            capped = growth in GROWTH_RANGE
            spread = (hi - lo) / price if pd.notna(lo) else np.nan
            score, label = confidence(p.land_deals_2023q1, spread, months_old_q1, 40 if capped else 60)
            reason = f"{p.land_deals_2023q1} land sales in this plan in {PLAN_QUARTER}, moved by the district's change"
            reason += " (change capped)" if capped else ""
        elif pd.notna(p.land_ppm2_2023q1):
            price = lo = hi = np.nan
            basis, score, label = "plan_2023q1_only_no_district_trend", 0, "none"
            reason = f"plan land price {int(p.land_ppm2_2023q1)} in {PLAN_QUARTER}; district has no trend to carry it"
        else:
            price = lo = hi = np.nan
            basis, score, label = "plan_listed_no_price", 0, "none"
            reason = f"{p.deals_2023q1} sales in {PLAN_QUARTER}, under {MIN_PLAN_DEALS} land sales; use the district price"
        placed = pd.notna(p.lng)
        rows.append({
            "unit_id": f"{p.city}:{p.district_id}:plan:{p.plan}", "level": "plan", "city": p.city, "city_ar": CITY_AR[p.city],
            "district_id": p.district_id, "district_ar": p.district_ar, "district_en": di.get("name_en", ""), "plan_no": p.plan,
            "sale_ppm2": r(price), "sale_ppm2_low": r(lo), "sale_ppm2_high": r(hi), "price_basis": basis,
            "deals_basis": int(p.land_deals_2023q1), "land_ppm2_est": r(price),
            "land_ppm2_2023q1": r(p.land_ppm2_2023q1), "district_ppm2_12m": r(di.get("ppm2_12m")),
            "district_growth_since_2023q1": r(growth, 2), "yoy_change": di.get("yoy", np.nan),
            "last_deal": di.get("last_deal", ""), "deals_2023q1": p.deals_2023q1,
            "asking_ppm2": r(p.asking_ppm2), "offers": p.offers,
            "ask_to_sold": r(p.asking_ppm2 / price, 2) if pd.notna(p.asking_ppm2) and pd.notna(price) else np.nan,
            "rent_apartment_year": di.get("rent_apt", np.nan),
            "lng": p.lng if placed else di.get("lng"), "lat": p.lat if placed else di.get("lat"),
            "geo_precision": "plan_point_from_offers" if placed else "district_centroid",
            "confidence": label, "confidence_score": score, "confidence_reason": reason,
            "sources": ";".join(["moj_deals", "na_districts"] + (["old_offers"] if p.offers else [])),
            "parcels_seen": p.parcels if pd.notna(p.parcels) else "", "data_as_of": AS_OF.isoformat(),
        })

    idx = pd.DataFrame(rows)
    cols = ["unit_id", "level", "city", "city_ar", "district_id", "district_ar", "district_en", "plan_no",
            "sale_ppm2", "sale_ppm2_low", "sale_ppm2_high", "price_basis", "deals_basis", "confidence",
            "confidence_score", "confidence_reason", "land_ppm2_est", "land_ppm2_2023q1", "district_ppm2_12m",
            "district_growth_since_2023q1", "yoy_change", "deals_12m", "value_12m_sar", "deals_total",
            "deals_2023q1", "last_deal", "asking_ppm2", "offers", "ask_to_sold", "rent_apartment_year",
            "rent_apartment_m2_year", "rent_contracts", "lng", "lat", "geo_precision", "parcels_seen", "sources",
            "data_as_of"]
    idx = idx[cols].sort_values(["city", "district_id", "level", "plan_no"], key=lambda c: c.map(
        {"district": 0, "plan": 1}) if c.name == "level" else c).reset_index(drop=True)
    for c in ["district_id", "deals_basis", "confidence_score", "deals_12m", "value_12m_sar", "deals_total",
              "deals_2023q1", "offers", "rent_contracts"]:
        idx[c] = idx[c].astype("Int64")
    idx.to_csv(out / "price_index.csv", index=False, encoding="utf-8-sig")

    rw = districts[["city", "district_id", "name_ar", "name_en"]].merge(rw, on="district_id")
    rw.to_csv(out / "rents_wide.csv", index=False, encoding="utf-8-sig")

    src = pd.DataFrame(SOURCES, columns=["source_id", "name", "gives", "finest_level", "license", "refresh",
                                         "status", "used_for"])
    src.to_csv(out / "sources.csv", index=False, encoding="utf-8-sig")

    cov = (idx.assign(priced=idx["sale_ppm2"].notna(), placed=idx["geo_precision"].eq("plan_point_from_offers"))
           .groupby(["city", "level"]).agg(units=("unit_id", "size"), priced=("priced", "sum"), placed_on_map=("placed", "sum"),
                                           high=("confidence", lambda c: (c == "high").sum()),
                                           medium=("confidence", lambda c: (c == "medium").sum()),
                                           low=("confidence", lambda c: (c == "low").sum()),
                                           none=("confidence", lambda c: (c == "none").sum())).reset_index())
    cov.to_csv(out / "coverage.csv", index=False, encoding="utf-8-sig")

    # ---- GeoJSON: district polygons + placed plan points ----
    def props(row):
        return {k: (None if pd.isna(v) else (int(v) if isinstance(v, (np.integer,)) else
                    float(v) if isinstance(v, np.floating) else v)) for k, v in row.items()}
    by_id = idx[idx["level"].eq("district")].set_index("district_id")
    feats = []
    for f in geo["features"]:
        did = f["properties"]["id"]
        if did in by_id.index:
            feats.append({"type": "Feature", "geometry": f["geometry"], "properties": props(by_id.loc[did].to_dict() | {"district_id": did})})
    for _, row in idx[idx["geo_precision"].eq("plan_point_from_offers")].iterrows():
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [row["lng"], row["lat"]]},
                      "properties": props(row.to_dict())})
    with open(out / "price_index.geojson", "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh, ensure_ascii=False, separators=(",", ":"))

    # ---- Excel workbook ----
    dictionary = pd.read_csv(Path(__file__).with_name("final_dictionary.csv"))
    readme = pd.DataFrame({"Nyyf Pro final dataset": [
        f"Built {datetime.now(timezone.utc).date().isoformat()} by data/pipelines/build_final.py from the base dataset. Data as of {AS_OF.isoformat()}.",
        "price_index: one row per district and per plan (مخطط). Use plan rows where they have a price, district rows otherwise.",
        "sale_ppm2 is the best current price per m² (SAR); sale_ppm2_low/high are the 25th and 75th percentiles.",
        "confidence (high/medium/low/none) and confidence_reason say how far to trust each price; sources lists what it rests on.",
        "Plan prices are 2023-Q1 land sales carried to today with the district's change, so they cap at medium confidence.",
        "Attribution: \"Ministry of Justice\" (deals), \"REGA\" (rents). Offers are for analysis only, not for republishing.",
        "Full deal list: deals_clean.csv.gz (too large for this workbook). Definitions: data_dictionary sheet.",
    ]})
    with pd.ExcelWriter(out / "nyyf_final.xlsx", engine="openpyxl") as xw:
        for name, df in [("README", readme), ("price_index", idx), ("rents_wide", rw), ("coverage", cov),
                         ("sources", src), ("data_dictionary", dictionary)]:
            df.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            ws.freeze_panes = "A2"
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in list(col)[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)

    print(cov.to_string(index=False))
    print({"price_index": len(idx), "deals": len(deals_out), "geojson_features": len(feats)})


if __name__ == "__main__":
    main()
