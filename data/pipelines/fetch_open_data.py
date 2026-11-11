"""Fetch the newest MOJ and REGA files straight from the Saudi Open Data Portal (open.data.gov.sa).

The weekly pipeline reads a community mirror (civillizard/saudi-real-estate-data), which can lag the portal by
months. This script builds a fresh tree in the mirror's layout, so the existing build scripts run on it
unchanged (point MOJ_REPO at --out):

  <out>/moj/sales/MOJ-Sales-<year>-Q<n>.csv         MOJ sale deals, one file per quarter
  <out>/rega/quarterlies/sales/<portal file name>   REGA sales transaction indicators by district
  <out>/rega/quarterlies/rental/<portal file name>  REGA rental indicators (Ejar)

It starts from the mirror (hard links, no copies) and adds every portal file the mirror does not have. Where
both hold the same quarter, the portal copy wins, since the portal is the source. MOJ files are matched by
quarter; REGA files by the region and quarter in their rows, because REGA file names drift (AlJawf / AlJouf,
1st-Q / Q1), so a portal file replaces the mirror's file for that region and quarter whatever either is called.
Two portal files for one quarter in a run are an error: the first stays, nothing is overwritten silently.

Each portal file goes through the same checks the build scripts apply, before it can enter the tree:
  * MOJ: at least half the deal dates must fall in the quarter the dataset names (the mirror once shipped
    2024-Q2 under the 2025-Q2 name). Otherwise the file is skipped.
  * REGA: the rows' quarter must be the one the file name says (build_rega_sales.py drops other rows).
  * Duplicates: a file whose rows mostly (over 50%) repeat a file already in the tree is a re-published copy
    and is skipped.
  * Completeness: a file with under 60% of the rows of the median of the four latest files of its series is
    flagged "partial". A partial MOJ quarter stays out (the MOJ build has no partial-quarter rule); a partial
    REGA file goes in, because build_rega_sales.py leaves incomplete quarters out itself and needs the file to
    see it.
Every decision is written to <out>/fetch_report.json and printed.

Only the portal's public metadata API and its odp-public file storage are used (see the mirror's
docs/OPEN_DATA_API.md); its download API blocks automated clients and is not used. Requests are spaced by
--delay seconds. Data is under the KSA Open Data License.

The portal resets connections from outside Saudi Arabia, so this must run on a machine with a Saudi IP:
a small VPS in a Saudi region or a self-hosted GitHub runner. For example, every Sunday at 05:00:

  0 5 * * 0  cd nyyf-pro && python3 data/pipelines/fetch_open_data.py \
               --mirror ~/saudi-real-estate-data --out ~/nyyf-open-data >> ~/fetch.log 2>&1

It is not part of the weekly workflow yet.

Usage:
  python data/pipelines/fetch_open_data.py --mirror <mirror clone> --out <dir> [--delay 2] [--check]
  --check only tests that the portal answers, and exits 0 or 1.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import re
import shutil
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PORTAL = "https://open.data.gov.sa"
ORGS = {"moj": "وزارة العدل", "rega": "الهيئة العامة للعقار"}
USER_AGENT = "nyyf-open-data-fetch/1.0 (open data mirror; polite rate)"

# Which datasets belong to which series, by their Arabic or English title.
SERIES = {
    "moj_sales": {
        "org": "moj",
        "dir": "moj/sales",
        "title": re.compile(r"صفقات البيع|transactions? (of )?sale|sale transactions", re.I),
        "skip": re.compile(r"مؤشر|indicator|إيجار|rent", re.I),
    },
    "rega_sales": {
        "org": "rega",
        "dir": "rega/quarterlies/sales",
        "title": re.compile(r"مؤشرات صفقات البيع|sales? transactions? indicators", re.I),
        "skip": None,
    },
    "rega_rental": {
        "org": "rega",
        "dir": "rega/quarterlies/rental",
        "title": re.compile(r"مؤشرات الإيجار|مؤشرات الايجار|rental indicators", re.I),
        "skip": None,
    },
}

MIN_IN_QUARTER = 0.5  # share of MOJ deal dates that must fall in the dataset's quarter
MAX_OVERLAP = 0.5  # share of rows repeating a file already in the tree that marks a copy
MIN_COMPLETE = 0.6  # rows against the median of the series' four latest files

ORDINALS = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "first": 1, "second": 2, "third": 3, "fourth": 4,
            "الأول": 1, "الاول": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4}


# ---------- Portal access ----------

class Portal:
    def __init__(self, base: str, delay: float):
        self.base = base.rstrip("/")
        self.delay = delay
        self.last = 0.0

    def get(self, path: str, timeout: int = 60) -> bytes:
        wait = self.delay - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(self.base + path, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
        finally:
            self.last = time.time()
        if body[:200].lower().find(b"request rejected") >= 0:
            raise RuntimeError(f"portal bot-filter rejected {path}")
        return body

    def json(self, path: str):
        return json.loads(self.get(path).decode("utf-8"))

    def datasets(self, org_name: str) -> list[dict]:
        q = urllib.parse.quote(org_name)
        data = self.json(f"/data/api/organizations?version=-1&organization={q}")
        return data.get("datasets", []) if isinstance(data, dict) else []

    def resources(self, dataset_id: str) -> tuple[dict, list[dict]]:
        d = self.json(f"/api/datasets/{dataset_id}")
        return d, [r for r in d.get("resources", []) if str(r.get("format", "")).upper() == "CSV" and r.get("url")]

    def download(self, url_path: str) -> bytes:
        parts = url_path.split("/")
        parts[-1] = urllib.parse.quote(parts[-1])
        return self.get("/odp-public/" + "/".join(parts), timeout=600)


# ---------- File naming and reading ----------

def quarter_of(text: str) -> str | None:
    """"2025-Q3" from a title or file name: "Q3 2025", "3rd-Q-2025", "1stQ-2025", "الربع الثالث 2025"."""
    t = text.replace("_", " ")
    year = re.search(r"(20\d\d)", t)
    if not year:
        return None
    for pat in (r"\bQ\s*-?\s*([1-4])\b", r"\b([1-4])\s*-?\s*Q\b"):
        m = re.search(pat, t, re.I)
        if m:
            return f"{year[1]}-Q{m[1]}"
    m = re.search(r"(1st|2nd|3rd|4th|first|second|third|fourth)\s*-?\s*(quarter|Q)", t, re.I)
    if m:
        return f"{year[1]}-Q{ORDINALS[m[1].lower()]}"
    m = re.search(r"الربع\s+(الأول|الاول|الثاني|الثالث|الرابع)", t)
    if m:
        return f"{year[1]}-Q{ORDINALS[m[1]]}"
    return None


def safe_name(name: str) -> str:
    name = re.sub(r"\s+", "-", name.strip())
    name = re.sub(r"[^\w.\-]", "", name)
    return name if name.lower().endswith(".csv") else name + ".csv"


def rows_of(body: bytes) -> tuple[list[str], list[list[str]]]:
    text = body.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(reader, [])]
    return header, [r for r in reader if any(c.strip() for c in r)]


def parse_date(s: str):
    s = s.strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def moj_quarter_share(header: list[str], rows: list[list[str]], claimed: str):
    """Share of deals dated in the claimed quarter, and the quarter most deals fall in."""
    col = next((header.index(h) for h in ("تاريخ الصفقة ميلادي", "التاريخ") if h in header), None)
    if col is None:
        return 0.0, None
    counts: dict[str, int] = {}
    for r in rows:
        d = parse_date(r[col]) if col < len(r) else None
        if d:
            q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
            counts[q] = counts.get(q, 0) + 1
    total = sum(counts.values())
    if not total:
        return 0.0, None
    return counts.get(claimed, 0) / total, max(counts, key=counts.get)


def fingerprints(rows: list[list[str]]) -> set[tuple]:
    return {tuple(c.strip() for c in r) for r in rows}


def read_local(path: Path) -> tuple[list[str], list[list[str]]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = [h.strip() for h in next(reader, [])]
        return header, [r for r in reader if any(c.strip() for c in r)]


class Tree:
    """The files of one output folder, read once: rows, fingerprints and (for REGA) the region and quarter
    their rows hold."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.cache: dict[str, dict] = {}

    def files(self) -> list[Path]:
        return sorted(f for f in self.folder.iterdir() if f.name.endswith((".csv", ".csv.gz")))

    def info(self, f: Path) -> dict:
        if f.name not in self.cache:
            header, rows = read_local(f)
            self.cache[f.name] = {"rows": len(rows), "prints": fingerprints(rows), "key": rega_key(header, rows)}
        return self.cache[f.name]

    def forget(self, name: str):
        self.cache.pop(name, None)


def rega_key(header: list[str], rows: list[list[str]]):
    """(region, quarter) most rows of a REGA file belong to, from its own columns, or None.

    File names drift (AlJawf / AlJouf, 1st-Q / Q1), so files are matched by what they hold."""
    h = [c.strip() for c in header]
    if not {"السنة", "الربع", "المنطقة"} <= set(h):
        return None
    iy, iq, ir = h.index("السنة"), h.index("الربع"), h.index("المنطقة")
    counts: dict[tuple, int] = {}
    for r in rows:
        if len(r) > max(iy, iq, ir) and r[iq].strip() in "1234" and r[iq].strip():
            k = (r[ir].strip(), f"{r[iy].strip()}-Q{r[iq].strip()}")
            counts[k] = counts.get(k, 0) + 1
    return max(counts, key=counts.get) if counts else None


def series_key(name: str) -> str:
    """Files of one series share a name without the quarter: "Rental-indicators-in-Riyadh-region", "MOJ-Sales"."""
    name = re.sub(r"\.csv(\.gz)?$", "", name, flags=re.I)
    name = re.sub(r"[-_ ]*((1st|2nd|3rd|4th)[-_ ]?Q|Q[1-4])[-_ ]?(20\d\d)$", "", name, flags=re.I)
    name = re.sub(r"[-_ ]*20\d\d[-_ ]?Q[1-4]$", "", name, flags=re.I)
    return name.lower()


# ---------- Tree ----------

def seed_from_mirror(mirror: Path | None, out: Path):
    """Link the mirror's files into the output tree, so unchanged files cost no space."""
    for s in SERIES.values():
        dst = out / s["dir"]
        dst.mkdir(parents=True, exist_ok=True)
        src = mirror / s["dir"] if mirror else None
        if not src or not src.is_dir():
            continue
        for f in src.glob("*.csv*"):
            target = dst / f.name
            if target.exists():
                continue
            try:
                os.link(f, target)
            except OSError:
                shutil.copy2(f, target)


def fetch(portal: Portal, out: Path, mirror: Path | None) -> list[dict]:
    seed_from_mirror(mirror, out)
    trees = {k: Tree(out / s["dir"]) for k, s in SERIES.items()}
    written: dict[str, str] = {}  # file name -> dataset that wrote it in this run
    report = []
    for org_key, org_name in ORGS.items():
        try:
            datasets = portal.datasets(org_name)
        except Exception as e:  # noqa: BLE001 - the portal is flaky; the mirror stays as the fallback
            report.append({"org": org_key, "status": "error", "reason": f"dataset list failed: {e}"})
            continue
        for ds in datasets:
            title = f"{ds.get('titleAr') or ''} {ds.get('title') or ''}"
            for key, s in SERIES.items():
                if s["org"] != org_key or not s["title"].search(title) or (s["skip"] and s["skip"].search(title)):
                    continue
                try:
                    _, resources = portal.resources(ds["id"])
                except Exception as e:  # noqa: BLE001
                    report.append({"series": key, "dataset": title.strip(), "status": "error", "reason": str(e)})
                    continue
                for res in resources:
                    report.append(take(portal, trees[key], key, title, res, written))
    return report


def remove(tree: Tree, f: Path):
    """Drop a file from the output tree (for a mirror file this removes the link, never the mirror's copy)."""
    f.unlink()
    tree.forget(f.name)


def take(portal: Portal, tree: Tree, key: str, title: str, res: dict, written: dict) -> dict:
    portal_name = res["url"].split("/")[-1]
    claimed = quarter_of(portal_name) or quarter_of(title)
    entry = {"series": key, "dataset": title.strip(), "portal_file": portal_name, "quarter": claimed}
    if not claimed:
        return {**entry, "status": "skipped", "reason": "no quarter in the title or file name"}
    name = f"MOJ-Sales-{claimed}.csv" if key == "moj_sales" else safe_name(portal_name)
    entry["file"] = name
    if name in written:
        # Two resources for one quarter: keep the first and say so, never silently overwrite.
        return {**entry, "status": "error", "reason": f"a second file for {name} in this run (first: {written[name]})"}
    try:
        body = portal.download(res["url"])
    except Exception as e:  # noqa: BLE001
        return {**entry, "status": "error", "reason": f"download failed: {e}"}
    header, rows = rows_of(body)
    entry["rows"] = len(rows)
    if not rows:
        return {**entry, "status": "skipped", "reason": "empty file"}

    if key == "moj_sales":
        share, found = moj_quarter_share(header, rows, claimed)
        entry["in_quarter"] = round(share, 3)
        if share < MIN_IN_QUARTER:
            return {**entry, "status": "skipped", "reason": f"dates belong to {found}, not {claimed}"}
        same_key = [f for f in tree.files() if f.name == name]
    else:
        rkey = rega_key(header, rows)
        if not rkey:
            return {**entry, "status": "skipped", "reason": "no year, quarter and region columns"}
        entry["region"], entry["quarter"] = rkey
        if rkey[1] != claimed:
            # build_rega_sales drops rows whose quarter differs from the file name's, so such a file would
            # only replace good data with nothing (the portal once filed Q2 rows as Hail-3rd-Q-2025).
            return {**entry, "status": "skipped", "reason": f"rows are {rkey[1]}, the name says {claimed}"}
        # The file in the tree that holds the same region and quarter, whatever its name.
        same_key = [f for f in tree.files() if tree.info(f)["key"] == rkey]

    prints = fingerprints(rows)
    for other in tree.files():
        if other in same_key:
            continue
        overlap = len(prints & tree.info(other)["prints"]) / len(prints)
        if overlap > MAX_OVERLAP:
            return {**entry, "status": "skipped", "reason": f"{overlap:.0%} of rows repeat {other.name}"}

    # Completeness against the latest files of the same series (MOJ: other quarters; REGA: same region).
    if key == "moj_sales":
        peers = [f for f in tree.files() if f.name != name and series_key(f.name) == series_key(name)]
    else:
        peers = [f for f in tree.files() if f not in same_key and (tree.info(f)["key"] or ("",))[0] == entry["region"]]
    peers = sorted(peers, key=lambda f: (tree.info(f)["key"] or ("", quarter_of(f.name) or ""))[1])[-4:]
    if peers:
        usual = statistics.median(tree.info(f)["rows"] for f in peers)
        entry["completeness"] = round(len(rows) / usual, 2) if usual else None
        if usual and len(rows) < MIN_COMPLETE * usual:
            entry["flag"] = "partial"
            if key == "moj_sales":
                # The MOJ build has no partial-quarter rule, so a short MOJ quarter stays out until it fills.
                return {**entry, "status": "skipped", "reason": f"partial: {len(rows)} rows, usually {int(usual)}"}

    written[name] = title.strip()
    if any(f.read_bytes() == body for f in same_key):
        return {**entry, "status": "same as mirror"}
    for f in same_key:
        remove(tree, f)  # the portal file replaces whatever held this quarter (and region)
    target = tree.folder / name
    if target.exists():
        remove(tree, target)
    target.write_bytes(body)
    return {**entry, "status": "replaced" if same_key else "added", "replaces": [f.name for f in same_key] or None}


def latest(out: Path) -> dict:
    """Newest quarter per series in the output tree."""
    res = {}
    for key, s in SERIES.items():
        qs = [q for q in (quarter_of(f.name) for f in (out / s["dir"]).glob("*.csv*")) if q]
        res[key] = max(qs) if qs else None
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mirror", type=Path, help="clone of civillizard/saudi-real-estate-data (the fallback)")
    ap.add_argument("--out", type=Path, help="output tree in the mirror's layout (use as MOJ_REPO)")
    ap.add_argument("--portal", default=PORTAL, help="portal base URL")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    ap.add_argument("--check", action="store_true", help="only test that the portal answers")
    args = ap.parse_args()

    portal = Portal(args.portal, args.delay)
    if args.check:
        try:
            n = len(portal.datasets(ORGS["moj"]))
            print(f"portal answers: {n} MOJ datasets")
            sys.exit(0 if n else 1)
        except Exception as e:  # noqa: BLE001
            print(f"portal unreachable: {e} (it only answers Saudi IPs)")
            sys.exit(1)
    if not args.out:
        ap.error("--out is required")

    before = latest(args.mirror) if args.mirror else {}
    report = fetch(portal, args.out, args.mirror)
    after = latest(args.out)
    for r in report:
        if r.get("status") not in ("same as mirror",):
            print(f"{r.get('status', ''):15} {r.get('series', r.get('org', '')):12} {r.get('file') or r.get('portal_file') or ''}"
                  f"{'  [' + r['flag'] + ']' if r.get('flag') else ''}  {r.get('reason', '')}")
    for k in SERIES:
        print(f"{k:12} mirror {before.get(k)}  ->  now {after.get(k)}")
    (args.out / "fetch_report.json").write_text(
        json.dumps({"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "latest": after,
                    "mirror_latest": before, "files": report}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    if any(r.get("status") == "error" for r in report) and not any(r.get("status") in ("added", "replaced", "same as mirror") for r in report):
        sys.exit(1)  # nothing reached: the portal is down or blocks this IP


if __name__ == "__main__":
    main()
