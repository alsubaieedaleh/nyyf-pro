"""Carry the official portal files from the Saudi runner to the weekly heat map build.

open.data.gov.sa only answers Saudi IPs, so fetch_open_data.py runs on a self-hosted runner in Saudi Arabia
(.github/workflows/open-data-portal.yml). That runner hands on only the portal files that are new or replace a
mirror file (a few MB, not the whole tree) as the artifact "portal-overlay"; heatmap-data.yml, on GitHub's own runner,
lays them over its mirror clone before fetch_latest.py. Stdlib only, and every command works the same in bash and
PowerShell, since the Saudi runner may be a Windows PC.

  mirror  --dest <dir>                 clone the mirror at the commit pinned in sources.lock.json (kept between runs)
  pack    --tree <fetch out> --out <dir>   copy the "added"/"replaced" files and fetch_report.json, write a summary
  apply   --overlay <dir> --tree <mirror>  check every file first, then replace what the report says, print a summary

The report's checks (quarter dates, duplicates, completeness) were already applied on the runner; apply re-checks
only that each file is there and is non-empty CSV, so a broken artifact changes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fetch_open_data import SERIES  # noqa: E402  (series -> folder in the mirror layout)

TAKEN = ("added", "replaced")


def summary(text: str):
    """Print, and add to the GitHub step summary when running in Actions."""
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def mirror(dest: Path):
    lock = json.loads((HERE / "sources.lock.json").read_text(encoding="utf-8"))["mirror"]
    git = ["git", "-C", str(dest)]
    if (dest / ".git").is_dir():
        head = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if head == lock["commit"]:
            print(f"mirror already at {head[:9]} in {dest}")
            return
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").is_dir():
        subprocess.run(["git", "init", "-q", str(dest)], check=True)
    subprocess.run(git + ["fetch", "-q", "--depth", "1", lock["repo"], lock["commit"]], check=True)
    subprocess.run(git + ["checkout", "-q", "--force", "FETCH_HEAD"], check=True)
    print(f"mirror at {lock['commit'][:9]} ({lock.get('committed', '')}) in {dest}")


def load_report(folder: Path) -> dict:
    path = folder / "fetch_report.json"
    if not path.is_file():
        sys.exit(f"no fetch_report.json in {folder}")
    return json.loads(path.read_text(encoding="utf-8"))


def table(report: dict) -> str:
    lines = [f"Portal fetch {report.get('fetched_at', '?')}", "",
             "| series | mirror had | now |", "|---|---|---|"]
    for k in SERIES:
        lines.append(f"| {k} | {report.get('mirror_latest', {}).get(k)} | {report.get('latest', {}).get(k)} |")
    lines += ["", "| status | series | file | note |", "|---|---|---|---|"]
    for r in report.get("files", []):
        if r.get("status") == "same as mirror":
            continue
        note = " ".join(x for x in (r.get("flag"), f"ratio {r['completeness']}" if r.get("completeness") is not None
                                    else None, r.get("reason")) if x)
        lines.append(f"| {r.get('status')} | {r.get('series', r.get('org', ''))} | "
                     f"{r.get('file') or r.get('portal_file') or ''} | {note} |")
    return "\n".join(lines)


def pack(tree: Path, out: Path):
    report = load_report(tree)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in report.get("files", []):
        if r.get("status") not in TAKEN:
            continue
        rel = Path(SERIES[r["series"]]["dir"]) / r["file"]
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tree / rel, out / rel)
        n += 1
    shutil.copy2(tree / "fetch_report.json", out / "fetch_report.json")
    summary(table(report))
    summary(f"\n{n} portal file(s) packed for the heat map build.")


def apply(overlay: Path, tree: Path):
    report = load_report(overlay)
    todo = [r for r in report.get("files", []) if r.get("status") in TAKEN]
    # Check everything before touching the tree, so a broken artifact leaves the mirror as it was.
    for r in todo:
        src = overlay / SERIES[r["series"]]["dir"] / r["file"]
        if not src.is_file() or src.stat().st_size == 0 or b"," not in src.read_bytes()[:4096]:
            sys.exit(f"overlay file missing or not CSV: {src}; nothing applied")
    for r in todo:
        folder = tree / SERIES[r["series"]]["dir"]
        folder.mkdir(parents=True, exist_ok=True)
        for old in (r.get("replaces") or []):
            if (folder / old).exists():
                (folder / old).unlink()
        shutil.copy2(overlay / SERIES[r["series"]]["dir"] / r["file"], folder / r["file"])
    summary(f"### Official portal files (fetched {report.get('fetched_at', '?')} on the Saudi runner)")
    summary("\n".join(f"- {r['status']} {r['file']}" + (f" (replaces {', '.join(r['replaces'])})" if r.get("replaces")
                                                        else "") for r in todo) or "- none newer than the mirror")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mirror")
    m.add_argument("--dest", type=Path, required=True)
    p = sub.add_parser("pack")
    p.add_argument("--tree", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = sub.add_parser("apply")
    a.add_argument("--overlay", type=Path, required=True)
    a.add_argument("--tree", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "mirror":
        mirror(args.dest)
    elif args.cmd == "pack":
        pack(args.tree, args.out)
    else:
        apply(args.overlay, args.tree)


if __name__ == "__main__":
    main()
