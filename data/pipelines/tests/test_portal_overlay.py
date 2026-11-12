"""portal_overlay.py pack/apply round trip: python -m unittest data/pipelines/tests/test_portal_overlay.py"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "portal_overlay.py"


def run(*args):
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)


class PackApply(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # The Saudi runner's fetch output: one replaced MOJ quarter, one added REGA file, one skipped, one unchanged.
        tree = self.tmp / "open-tree"
        (tree / "moj/sales").mkdir(parents=True)
        (tree / "rega/quarterlies/sales").mkdir(parents=True)
        (tree / "moj/sales/MOJ-Sales-2025-Q2.csv").write_text("a,b\nportal,2025-05-01\n", encoding="utf-8")
        (tree / "moj/sales/MOJ-Sales-2024-Q1.csv").write_text("a,b\nmirror,2024-01-01\n", encoding="utf-8")
        (tree / "rega/quarterlies/sales/Hail-Q1-2026.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        (tree / "fetch_report.json").write_text(json.dumps({
            "fetched_at": "2026-11-15T00:30Z", "latest": {}, "mirror_latest": {},
            "files": [
                {"series": "moj_sales", "file": "MOJ-Sales-2025-Q2.csv", "status": "replaced",
                 "replaces": ["MOJ-Sales-2025-Q2.csv"]},
                {"series": "rega_sales", "file": "Hail-Q1-2026.csv", "status": "replaced",
                 "replaces": ["Hail-1st-Q-2026.csv"]},
                {"series": "moj_sales", "file": "MOJ-Sales-2026-Q3.csv", "status": "skipped",
                 "reason": "partial"},
                {"series": "moj_sales", "file": "MOJ-Sales-2024-Q1.csv", "status": "same as mirror"},
            ]}), encoding="utf-8")
        # The build's mirror clone.
        self.mirror = self.tmp / "mirror"
        (self.mirror / "moj/sales").mkdir(parents=True)
        (self.mirror / "rega/quarterlies/sales").mkdir(parents=True)
        (self.mirror / "moj/sales/MOJ-Sales-2025-Q2.csv").write_text("a,b\nmislabelled,2024-05-01\n", encoding="utf-8")
        (self.mirror / "rega/quarterlies/sales/Hail-1st-Q-2026.csv").write_text("x,y\nold,1\n", encoding="utf-8")
        self.overlay = self.tmp / "overlay"
        r = run("pack", "--tree", str(tree), "--out", str(self.overlay))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_pack_takes_only_new_files(self):
        files = sorted(p.relative_to(self.overlay).as_posix() for p in self.overlay.rglob("*") if p.is_file())
        self.assertEqual(files, ["fetch_report.json", "moj/sales/MOJ-Sales-2025-Q2.csv",
                                 "rega/quarterlies/sales/Hail-Q1-2026.csv"])

    def test_apply_replaces_by_report(self):
        r = run("apply", "--overlay", str(self.overlay), "--tree", str(self.mirror))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("portal", (self.mirror / "moj/sales/MOJ-Sales-2025-Q2.csv").read_text(encoding="utf-8"))
        self.assertFalse((self.mirror / "rega/quarterlies/sales/Hail-1st-Q-2026.csv").exists())
        self.assertTrue((self.mirror / "rega/quarterlies/sales/Hail-Q1-2026.csv").exists())

    def test_broken_overlay_changes_nothing(self):
        (self.overlay / "rega/quarterlies/sales/Hail-Q1-2026.csv").unlink()
        r = run("apply", "--overlay", str(self.overlay), "--tree", str(self.mirror))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("mislabelled", (self.mirror / "moj/sales/MOJ-Sales-2025-Q2.csv").read_text(encoding="utf-8"))
        self.assertTrue((self.mirror / "rega/quarterlies/sales/Hail-1st-Q-2026.csv").exists())


if __name__ == "__main__":
    unittest.main()
