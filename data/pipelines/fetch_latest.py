"""Build the freshest open-data tree the heat map can use, from pinned sources, with every file checked.

The weekly build reads a tree in the civillizard mirror's layout (MOJ_REPO). The mirror lags: its newest MOJ sale file
is 2026-Q1. Newer quarters of the same Ministry of Justice deals are published elsewhere under the same open licence
(the Ministry's public transactions report, republished as plain CSV). This script lays those quarters over the mirror
(or over a tree made by fetch_open_data.py from a Saudi connection) so the existing build scripts run unchanged:

  <out>/moj/sales/MOJ-Sales-<year>-Q<n>.csv   one file per quarter, in the Ministry's own column layout
  <out>/rega/...                              linked from the base tree, unchanged
  <out>/gastat/repi.xlsx                      GASTAT Real Estate Price Index tables (region x type, to the latest quarter)
  <out>/fetch_latest_report.json              every decision, per source and per city

Every input is pinned in sources.lock.json (URL at a fixed commit + sha256). A download that does not match its
checksum stops the run: nothing upstream can change the map without a reviewed lock bump.

Checks, for each overlay quarter:
  * Dates: at least 99% of a source's deals fall in the quarter it claims.
  * Two sources for one quarter must agree: 99% of the smaller one's refs are in the other, and under 0.1% of the
    shared refs differ in price or area. Then the union by ref is used (Ministry-layout rows win). One source alone
    is used but marked "single source" in the report.
  * Duplicates: a ref already in another quarter's file is dropped from the overlay.
  * The base wins when it already holds a complete file for the quarter (the official portal file is preferred).
  * Completeness: under 60% of the median rows of the four quarters before it marks the quarter partial and holds it
    out (rerun with --accept-partial after checking the printed ratio, as in fetch_open_data.py).
  * Per city: deals per quarter for every city in cities.json. A city whose newest quarter has under 40% of its usual
    count is reported as "thinning" (Riyadh: since 19 May 2026 its sales are registered only in the Real Estate
    Registry, which these files do not hold).

Usage:
  python data/pipelines/fetch_latest.py --base <mirror clone or fetch_open_data tree> --out <dir> [--cache <dir>]
                                        [--portal <open-portal-data checkout>]
  python data/pipelines/fetch_latest.py --discover     read-only: is there anything newer upstream than the lock?
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import statistics
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK = HERE / "sources.lock.json"
USER_AGENT = "nyyf-pro-data-pipeline/1.0 (open data; polite)"

# The Ministry's column layout (the mirror's MOJ-Sales files since 2023-Q4).
MOJ_HEADER = ["المنطقة", "المدينة", "المدينة / الحي", "الرقم المرجعي للصفقة", "تاريخ الصفقة ميلادي",
              "تاريخ الصفقة هجري", "تصنيف العقار", "عدد العقارات", "السعر", "المساحة"]
CLASS_AR = {"residential": "سكني", "commercial": "تجاري", "agricultural": "زراعي", "mixed": "سكني تجاري"}
# The Ministry's own region spellings, as in its files.
REGION_AR = {
    "Riyadh": "منطقة الرياض", "Makkah": "منطقة مكة المكرمه", "Madinah": "منطقة المدينة المنوره",
    "Eastern Province": "منطقة الشرقية", "Qassim": "منطقة القصيم", "Asir": "منطقة عسير", "Hail": "منطقة حائل",
    "Jazan": "منطقة جازان", "Tabuk": "منطقة تبوك", "Najran": "منطقة نجران", "Al Jouf": "منطقة الجوف",
    "Northern Borders": "منطقة الحدود الشمالية", "Al Baha": "منطقة الباحة",
}

MIN_IN_QUARTER = 0.99
MIN_REF_AGREEMENT = 0.99
MAX_VALUE_MISMATCH = 0.001
MIN_COMPLETE = 0.6
BASE_COMPLETE = 0.95  # the base's own file for a quarter wins when it has this share of the overlay's rows
THINNING = 0.4


# ---------- small helpers ----------

def num(s) -> float | None:
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def ref_of(s) -> str:
    return str(s or "").replace(",", "").strip()


def parse_date(s: str) -> date | None:
    s = (s or "").strip()[:10]
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})$", s)  # 2023-Q1 uses M/D/YYYY
    return date(int(m[3]), int(m[1]), int(m[2])) if m else None


def quarter(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def fold_city(s: str) -> str:
    aliases = {"الاحساء": "الهفوف", "الأحساء": "الهفوف", "مدينة المدينة المنورة": "المدينة المنورة"}
    s = aliases.get(s.strip(), s.strip())
    return s.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, want_sha: str, cache: Path) -> Path:
    """The file at url, from the cache when its checksum is there. A checksum mismatch is fatal."""
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / want_sha
    if target.exists() and sha256(target) == want_sha:
        return target
    tmp = cache / (want_sha + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    got = sha256(tmp)
    if got != want_sha:
        tmp.unlink()
        raise SystemExit(f"checksum mismatch for {url}: got {got}, lock says {want_sha}. "
                         "Upstream changed: review it, then bump sources.lock.json.")
    tmp.replace(target)
    return target


# ---------- reading the two layouts ----------

def read_csv(path: Path) -> list[dict]:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as fh:
        return [{(k or "").strip(): (v or "") for k, v in r.items()} for r in csv.DictReader(fh)]


def from_moj(rows: list[dict]) -> list[dict]:
    """Ministry layout -> normalised deal (the row itself is kept for writing back unchanged)."""
    out = []
    for r in rows:
        d = parse_date(r.get("تاريخ الصفقة ميلادي") or r.get("التاريخ") or "")
        ref = ref_of(r.get("الرقم المرجعي للصفقة") or r.get("رقم مرجعي"))
        if not d or not ref:
            continue
        out.append({"ref": ref, "date": d, "city": (r.get("المدينة") or "").strip(),
                    "price": num(r.get("السعر") or r.get("السعر بالريال السعودي")), "area": num(r.get("المساحة")),
                    "row": {h: r.get(h, "") for h in MOJ_HEADER}})
    return out


def from_ksald(rows: list[dict]) -> list[dict]:
    """KSA Land Data layout -> normalised deal, with the row rebuilt in the Ministry's layout. The Ministry fields
    (city, district, ref, date, class, count, price, area) pass through as published; the region goes back to the
    Ministry's spelling, and the Hijri date (unused by the builds) stays empty."""
    out = []
    for r in rows:
        d = parse_date(r.get("date", ""))
        ref = ref_of(r.get("ref_no"))
        if not d or not ref:
            continue
        city = (r.get("city_ar") or "").strip()
        district = (r.get("district_ar") or "").strip()
        price, area = num(r.get("price_sar")), num(r.get("area_sqm"))
        row = {
            "المنطقة": REGION_AR.get(r.get("region_en", ""), r.get("region_en", "")),
            "المدينة": city,
            "المدينة / الحي": f"{city}/ {district}",
            "الرقم المرجعي للصفقة": ref,
            "تاريخ الصفقة ميلادي": d.strftime("%Y/%m/%d"),
            "تاريخ الصفقة هجري": "",
            "تصنيف العقار": CLASS_AR.get(r.get("classification", ""), r.get("classification", "")),
            "عدد العقارات": r.get("properties_count") or "1",
            "السعر": f"{price:.2f}" if price is not None else "",
            "المساحة": f"{area:.2f}" if area is not None else "",
        }
        out.append({"ref": ref, "date": d, "city": city, "price": price, "area": area, "row": row})
    return out


def in_quarter_share(deals: list[dict], q: str) -> float:
    return sum(quarter(d["date"]) == q for d in deals) / len(deals) if deals else 0.0


def agreement(a: list[dict], b: list[dict]) -> dict:
    ra, rb = {d["ref"]: d for d in a}, {d["ref"]: d for d in b}
    common = ra.keys() & rb.keys()
    differ = sum(1 for k in common
                 if abs((ra[k]["price"] or 0) - (rb[k]["price"] or 0)) > 1
                 or abs((ra[k]["area"] or 0) - (rb[k]["area"] or 0)) > 1)
    small = min(len(ra), len(rb)) or 1
    return {"common": len(common), "only_first": len(ra.keys() - rb.keys()), "only_second": len(rb.keys() - ra.keys()),
            "ref_agreement": round(len(common) / small, 4), "value_mismatch": round(differ / (len(common) or 1), 5)}


# ---------- the tree ----------

def link_tree(base: Path, out: Path):
    """Hard-link (or copy) every csv of the base tree's moj/ and rega/ folders into out."""
    for sub in ("moj/sales", "rega/quarterlies/sales", "rega/quarterlies/rental"):
        src, dst = base / sub, out / sub
        dst.mkdir(parents=True, exist_ok=True)
        if not src.is_dir():
            continue
        for f in src.glob("*.csv*"):
            t = dst / f.name
            if t.exists():
                continue
            try:
                os.link(f, t)
            except OSError:
                shutil.copy2(f, t)


def moj_files(folder: Path) -> dict[str, Path]:
    """quarter -> file, for MOJ-Sales-YYYY-Qn.csv[.gz]."""
    out = {}
    for f in sorted(folder.glob("MOJ-Sales-20*.csv*")):
        m = re.search(r"(20\d\d)-Q([1-4])", f.name)
        if m:
            out[f"{m[1]}-Q{m[2]}"] = f
    return out


def file_deals(path: Path) -> list[dict]:
    return from_moj(read_csv(path))


def write_moj(path: Path, deals: list[dict]):
    if path.exists() or path.is_symlink():
        path.unlink()  # never write through a hard link into the base tree
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MOJ_HEADER)
        w.writeheader()
        for d in sorted(deals, key=lambda d: (d["date"], d["ref"])):
            w.writerow(d["row"])


def prev_quarters(q: str, n: int) -> list[str]:
    y, k = int(q[:4]), int(q[-1])
    out = []
    for _ in range(n):
        k -= 1
        if k == 0:
            y, k = y - 1, 4
        out.append(f"{y}-Q{k}")
    return out


# ---------- main steps ----------

def apply_portal(portal: Path, out: Path) -> dict:
    """Lay the official portal files fetched from a Saudi machine (fetch_open_data.py --delta, published to the
    open-portal-data branch) over the linked tree. They were checked there (quarter, copies, completeness); each
    replaces the mirror file(s) its report names."""
    rep = json.loads((portal / "fetch_report.json").read_text(encoding="utf-8"))
    dirs = {"moj_sales": "moj/sales", "rega_sales": "rega/quarterlies/sales", "rega_rental": "rega/quarterlies/rental"}
    applied = []
    for r in rep.get("files", []):
        if r.get("status") not in ("added", "replaced") or not r.get("file") or r.get("series") not in dirs:
            continue
        folder = out / dirs[r["series"]]
        src = portal / dirs[r["series"]] / r["file"]
        if not src.exists():
            raise SystemExit(f"portal delta lists {r['file']} but the file is missing")
        for old in [*(r.get("replaces") or []), r["file"]]:
            for f in folder.glob(old + "*"):
                f.unlink()  # unlink only: the base tree behind the hard link is untouched
        shutil.copy2(src, folder / r["file"])
        applied.append({"file": r["file"], "status": r["status"], "replaces": r.get("replaces"), "rows": r.get("rows")})
    return {"fetched_at": rep.get("fetched_at"), "latest": rep.get("latest"), "applied": applied}


def build(base: Path, out: Path, cache: Path, lock: dict, accept_partial: bool = False,
          portal: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    link_tree(base, out)
    sales = out / "moj" / "sales"
    report: dict = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "base": str(base), "lock": {"mirror_commit": lock["mirror"]["commit"]}, "quarters": [], "warnings": []}
    if portal and (portal / "fetch_report.json").exists():
        report["portal"] = apply_portal(portal, out)

    by_quarter: dict[str, list[dict]] = defaultdict(list)
    for src in lock.get("moj_overlays", []):
        by_quarter[src["quarter"]].append(src)

    preliminary = sorted({m for s in lock.get("moj_overlays", []) for m in s.get("preliminary_months", [])})
    for q in sorted(by_quarter):
        entry = {"quarter": q, "sources": [], "decision": None}
        loaded = []
        for src in by_quarter[q]:
            path = download(src["url"], src["sha256"], cache)
            rows = read_csv(path)
            deals = (from_moj if src["layout"] == "moj" else from_ksald)(rows)
            share = in_quarter_share(deals, q)
            info = {"id": src["id"], "rows": len(rows), "deals": len(deals), "in_quarter": round(share, 4),
                    "sha256": src["sha256"]}
            if src.get("rows") and len(rows) != src["rows"]:
                info["note"] = f"lock says {src['rows']} rows"
            if share < MIN_IN_QUARTER:
                info["status"] = "rejected: dates outside the quarter"
                entry["sources"].append(info)
                continue
            deals = [d for d in deals if quarter(d["date"]) == q]
            info["status"] = "ok"
            entry["sources"].append(info)
            loaded.append((src, deals))
        if not loaded:
            entry["decision"] = "no usable source"
            report["quarters"].append(entry)
            continue

        # Cross-check every pair of sources for the quarter.
        for i in range(len(loaded)):
            for j in range(i + 1, len(loaded)):
                ag = agreement(loaded[i][1], loaded[j][1])
                ag["pair"] = [loaded[i][0]["id"], loaded[j][0]["id"]]
                entry.setdefault("agreement", []).append(ag)
                if ag["ref_agreement"] < MIN_REF_AGREEMENT or ag["value_mismatch"] > MAX_VALUE_MISMATCH:
                    raise SystemExit(f"{q}: sources {ag['pair']} disagree ({ag}). Not publishing a quarter two "
                                     "copies of the same Ministry data cannot agree on.")
        # Union by ref; Ministry-layout rows first, so they win.
        loaded.sort(key=lambda sd: sd[0]["layout"] != "moj")
        merged: dict[str, dict] = {}
        for _, deals in loaded:
            for d in deals:
                merged.setdefault(d["ref"], d)
        entry["single_source"] = len(loaded) == 1
        entry["merged"] = len(merged)

        # Refs already in another quarter's file are not new deals.
        existing = moj_files(sales)
        other_refs = set()
        for oq, f in existing.items():
            if oq != q:
                other_refs |= {d["ref"] for d in file_deals(f)}
        dup = [r for r in merged if r in other_refs]
        for r in dup:
            del merged[r]
        entry["dropped_cross_quarter_duplicates"] = len(dup)

        # The base's own file wins when it is complete.
        if q in existing:
            base_deals = [d for d in file_deals(existing[q]) if quarter(d["date"]) == q]
            ok_dates = in_quarter_share(file_deals(existing[q]), q) >= 0.5
            if ok_dates and len(base_deals) >= BASE_COMPLETE * len(merged):
                entry["decision"] = f"kept base file {existing[q].name} ({len(base_deals)} deals)"
                entry["base_vs_overlay"] = agreement(base_deals, list(merged.values()))
                report["quarters"].append(entry)
                continue
            entry["replaces"] = f"{existing[q].name} ({len(base_deals)} deals in its quarter)"

        # Completeness against the four quarters before it.
        counts = [sum(1 for d in file_deals(existing[p]) if quarter(d["date"]) == p)
                  for p in prev_quarters(q, 4) if p in existing]
        med = statistics.median(counts) if counts else None
        ratio = round(len(merged) / med, 2) if med else None
        entry["ratio_to_recent_median"] = ratio
        if ratio is not None and ratio < MIN_COMPLETE and not accept_partial:
            entry["decision"] = f"held out: partial ({ratio} of the recent median); rerun with --accept-partial"
            report["quarters"].append(entry)
            continue

        target = sales / f"MOJ-Sales-{q}.csv"
        for f in sales.glob(f"MOJ-Sales-{q}.csv*"):
            f.unlink()
        write_moj(target, list(merged.values()))
        entry["decision"] = f"wrote {target.name} ({len(merged)} deals)"
        months = sorted({d['date'].strftime('%Y-%m') for d in merged.values()})
        entry["preliminary_months"] = [m for m in months if m in preliminary]
        report["quarters"].append(entry)

    report["preliminary_months"] = preliminary
    report["cities"] = city_coverage(sales, report)

    # GASTAT price index (regional, by type) to the latest quarter.
    g = lock.get("gastat_repi")
    if g:
        path = download(g["url"], g["sha256"], cache)
        (out / "gastat").mkdir(exist_ok=True)
        shutil.copy2(path, out / "gastat" / "repi.xlsx")
        report["gastat_repi"] = {"quarter": g["quarter"], "file": "gastat/repi.xlsx"}

    report["newest_deal"] = newest_deal(sales)
    (out / "fetch_latest_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def newest_deal(sales: Path) -> str | None:
    files = moj_files(sales)
    if not files:
        return None
    q = max(files)
    ds = [d["date"] for d in file_deals(files[q]) if quarter(d["date"]) == q]
    return max(ds).isoformat() if ds else None


def city_coverage(sales: Path, report: dict) -> dict:
    cities = json.loads((HERE / "cities.json").read_text(encoding="utf-8"))
    files = moj_files(sales)
    recent = sorted(files)[-6:]
    want = {fold_city(c["ar"]): c["slug"] for c in cities}
    counts: dict[str, Counter] = defaultdict(Counter)
    for q in recent:
        for d in file_deals(files[q]):
            slug = want.get(fold_city(d["city"]))
            if slug and quarter(d["date"]) == q:
                counts[slug][q] += 1
    out = {}
    for c in cities:
        row = {q: counts[c["slug"]].get(q, 0) for q in recent}
        newest = recent[-1] if recent else None
        before = [row[q] for q in recent[-5:-1]]
        med = statistics.median(before) if before else 0
        ratio = round(row[newest] / med, 2) if med else None
        status = "thinning" if ratio is not None and ratio < THINNING else "ok"
        out[c["slug"]] = {"deals": row, "newest_vs_median": ratio, "status": status}
        if status == "thinning":
            report["warnings"].append(f"{c['slug']}: newest quarter has {row[newest]} deals, {ratio} of its recent "
                                      "median. Its sales are likely moving to the Real Estate Registry.")
    return out


def discover(lock: dict) -> dict:
    """Read-only: what is newer upstream than the lock? Nothing is changed."""
    found = {}

    def get(url, accept="application/json"):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()

    newest = max(s["quarter"] for s in lock.get("moj_overlays", [])) if lock.get("moj_overlays") else None
    try:
        meta = json.loads(get(lock["watch"]["ksald_meta"]))
        qs = [f"{q[:4]}-{q[4:]}" for q in meta.get("quarters", [])]
        found["moj_quarters_published"] = qs[-3:]
        found["moj_newer_than_lock"] = [q for q in qs if newest and q > newest]
        found["moj_preliminary_months"] = meta.get("preliminary_months", [])
    except Exception as e:  # noqa: BLE001 - discovery is advisory
        found["moj_error"] = str(e)
    try:
        ds = lock["watch"]["hf_dataset"]
        commits = json.loads(get(f"https://huggingface.co/api/datasets/{ds}/commits/main"))
        found["hf_latest_commit"] = {"id": commits[0]["id"], "date": commits[0]["date"], "title": commits[0]["title"]}
    except Exception as e:  # noqa: BLE001
        found["hf_error"] = str(e)
    try:
        head = json.loads(get(lock["mirror"]["repo"].replace("https://github.com/", "https://api.github.com/repos/")
                              + "/commits?per_page=1"))
        found["mirror_head"] = {"sha": head[0]["sha"], "date": head[0]["commit"]["committer"]["date"],
                                "newer_than_lock": head[0]["sha"] != lock["mirror"]["commit"]}
    except Exception as e:  # noqa: BLE001
        found["mirror_error"] = str(e)
    g = lock.get("gastat_repi")
    if g:
        y, k = int(g["quarter"][:4]), int(g["quarter"][-1])
        y, k = (y + 1, 1) if k == 4 else (y, k + 1)
        url = lock["watch"]["gastat_next"].format(q=f"q{k}", y=y)
        try:
            body = get(url, accept="*/*")
            found["gastat_next"] = {"quarter": f"{y}-Q{k}", "available": body[:2] == b"PK", "url": url}
        except Exception:  # noqa: BLE001
            found["gastat_next"] = {"quarter": f"{y}-Q{k}", "available": False, "url": url}
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, help="mirror clone, or a tree made by fetch_open_data.py")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--cache", type=Path, default=Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "nyyf-source-cache")
    ap.add_argument("--lock", type=Path, default=LOCK)
    ap.add_argument("--accept-partial", action="store_true")
    ap.add_argument("--portal", type=Path, help="official portal files from the Saudi runner (open-portal-data branch)")
    ap.add_argument("--discover", action="store_true", help="only report what is newer upstream than the lock")
    args = ap.parse_args()
    lock = json.loads(args.lock.read_text(encoding="utf-8"))

    if args.discover:
        print(json.dumps(discover(lock), ensure_ascii=False, indent=1))
        return
    if not args.base or not args.out:
        ap.error("--base and --out are needed (or --discover)")
    rep = build(args.base, args.out, args.cache, lock, args.accept_partial, args.portal)
    if rep.get("portal"):
        p = rep["portal"]
        print(f"Official portal files fetched {p['fetched_at']}: {len(p['applied'])} applied")
        for a in p["applied"]:
            print(f"  {a['status']:9} {a['file']}" + (f" (replaces {', '.join(a['replaces'])})" if a.get("replaces") else ""))
    for e in rep["quarters"]:
        extra = " single source" if e.get("single_source") else ""
        prelim = f" preliminary {','.join(e['preliminary_months'])}" if e.get("preliminary_months") else ""
        print(f"{e['quarter']}: {e['decision']}{extra}{prelim}")
        for a in e.get("agreement", []):
            print(f"  {a['pair'][0]} vs {a['pair'][1]}: {a['common']} shared refs, agreement {a['ref_agreement']:.2%}, "
                  f"value mismatch {a['value_mismatch']:.3%}")
    print(f"Newest MOJ deal: {rep['newest_deal']}")
    for w in rep["warnings"]:
        print(f"WARNING: {w}")
    if rep.get("gastat_repi"):
        print(f"GASTAT price index to {rep['gastat_repi']['quarter']}")


if __name__ == "__main__":
    sys.exit(main())
