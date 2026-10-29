"""Check which public Amanah / Balady ArcGIS map services publish plan (مخطط) or parcel layers.

ArcGIS REST services directories are published for programmatic use. This script reads them
read-only and lightly (one request per page, a pause between requests), identifies itself
honestly, and stops at whatever a server refuses. It does not touch sites that block automated
clients (SREM, for one): data from those should come through an official channel.

Needs network access to the hosts below (Allowed domains in the cloud environment settings).
Writes a JSON report to --out and prints a summary. Reuse terms of each layer still need to be
confirmed with the Amanah before any data is stored or shown.

Usage:
  python data/pipelines/probe_gov_sources.py --out data/raw/probe.json
"""

import argparse
import json
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path

ARCGIS_ROOTS = [
    "https://webgis.eamana.gov.sa/arcgisnew/rest/services",
    "https://umaps.balady.gov.sa/server/rest/services",
    "https://umaps.balady.gov.sa/arcgis/rest/services",
    # umaps.balady.gov.sa now redirects to the MOMAH host (checked 2026-10-29)
    "https://umaps.momah.gov.sa/server/rest/services",
    "https://umaps.momah.gov.sa/arcgis/rest/services",
]
HEADERS = {"User-Agent": "nyyf-pro-data-probe/0.1 (+https://github.com/alsubaieedaleh/nyyf-pro)", "Accept": "application/json"}
PLAN_LAYER = re.compile(r"plan|parcel|land|subdiv|مخطط|قطع|أراضي|اراضي|قطعة", re.I)
PAUSE_S = 1.0
MAX_SERVICES = 60


def get(url):
    time.sleep(PAUSE_S)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as res:
            return {"status": res.status, "json": json.loads(res.read())}
    except urllib.error.HTTPError as e:
        return {"status": e.code}
    except Exception as e:  # network refusals and non-JSON pages land here
        return {"status": None, "error": str(e)}


def robots_allow(root):
    host = "/".join(root.split("/")[:3])
    rp = urllib.robotparser.RobotFileParser(f"{host}/robots.txt")
    try:
        rp.read()
    except Exception:
        return True  # no readable robots.txt: the request below reports any refusal
    return rp.can_fetch(HEADERS["User-Agent"], f"{root}?f=json")


def probe_arcgis(root):
    report = {"root": root, "services": [], "plan_layers": []}
    if not robots_allow(root):
        report["error"] = "robots.txt disallows automated access; ask the owner instead"
        return report
    top = get(f"{root}?f=json")
    report["status"] = top.get("status")
    if "json" not in top:
        report["error"] = top.get("error")
        return report
    services = list(top["json"].get("services", []))
    for folder in top["json"].get("folders", []):
        services += get(f"{root}/{folder}?f=json").get("json", {}).get("services", [])
    report["services"] = [f"{s['name']} ({s['type']})" for s in services]
    for s in services[:MAX_SERVICES]:
        if s["type"] not in ("MapServer", "FeatureServer"):
            continue
        meta = get(f"{root}/{s['name']}/{s['type']}?f=json").get("json", {})
        for layer in meta.get("layers", []):
            if not PLAN_LAYER.search(layer.get("name", "")):
                continue
            url = f"{root}/{s['name']}/{s['type']}/{layer['id']}"
            info = get(f"{url}?f=json").get("json", {})
            report["plan_layers"].append({
                "url": url,
                "name": layer.get("name"),
                "fields": [f.get("name") for f in info.get("fields", [])],
                "max_records": info.get("maxRecordCount"),
                "copyright": info.get("copyrightText"),
                "description": (info.get("description") or "")[:300],
            })
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    report = [probe_arcgis(r) for r in ARCGIS_ROOTS]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for a in report:
        print(f"{a['root']}: {a.get('status')} services {len(a['services'])}, plan layers {len(a['plan_layers'])} {a.get('error', '')}")
        for layer in a["plan_layers"]:
            print(f"  {layer['name']}: fields {layer['fields'][:12]}, copyright {layer['copyright']!r}")


if __name__ == "__main__":
    main()
