"""Tests for fetch_latest.py and the report's whole-window rule: python -m unittest discover data/pipelines/tests"""

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import build_moj_market  # noqa: E402
import build_report  # noqa: E402
import fetch_latest as fl  # noqa: E402

KSALD_H = ["quarter", "date", "region_slug", "region_en", "city_slug", "city_en", "city_ar", "district_ar",
           "classification", "property_type", "properties_count", "price_sar", "area_sqm", "price_per_sqm", "ref_no"]


def write(path: Path, header, rows, bom=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def moj_rows(y, q, n, start=0, city="جده", price=500000):
    m0 = (q - 1) * 3 + 1
    return [["منطقة مكة المكرمه", city, f"{city}/ حي الروضة ", f"{y}{q}{i:05d}",
             f"{y}/{m0 + i % 3:02d}/{1 + i % 28:02d}", "", "سكني", "1", f"{price + i:,}", "500.00"]
            for i in range(start, start + n)]


def ksald_rows(y, q, n, start=0, city="جده", price=500000):
    m0 = (q - 1) * 3 + 1
    return [[f"{y}Q{q}", f"{y}-{m0 + i % 3:02d}-{1 + i % 28:02d}", "makkah", "Makkah", "jeddah", "Jeddah", city,
             "حي الروضة", "residential", "", "1", f"{price + i}.0", "500.0", "1000.0", f"{y}{q}{i:05d}"]
            for i in range(start, start + n)]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class FetchLatestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "mirror"
        for y, q in [(2025, 3), (2025, 4), (2026, 1)]:
            write(self.base / "moj/sales" / f"MOJ-Sales-{y}-Q{q}.csv", fl.MOJ_HEADER, moj_rows(y, q, 100))
        (self.base / "rega/quarterlies/rental").mkdir(parents=True)
        write(self.base / "rega/quarterlies/rental/Rental-x-1st-Q-2026.csv", ["السنة"], [["2026"]])
        self.src = self.tmp / "src"

    def lock(self, *overlays):
        return {"mirror": {"commit": "abc"}, "moj_overlays": list(overlays)}

    def overlay(self, sid, quarter, layout, path, **kw):
        return {"id": sid, "quarter": quarter, "layout": layout, "url": path.resolve().as_uri(), "sha256": sha(path), **kw}

    def run_build(self, lock, accept_partial=False):
        out = self.tmp / "out"
        return out, fl.build(self.base, out, self.tmp / "cache", lock, accept_partial)

    def test_two_agreeing_sources_merge_into_the_ministry_layout(self):
        a = write(self.src / "raw.csv", fl.MOJ_HEADER, moj_rows(2026, 2, 100), bom=True)
        b = write(self.src / "ksald.csv", KSALD_H, ksald_rows(2026, 2, 101))  # one more deal than a
        out, rep = self.run_build(self.lock(self.overlay("raw", "2026-Q2", "moj", a),
                                            self.overlay("ksald", "2026-Q2", "ksald", b)))
        q = rep["quarters"][0]
        self.assertEqual(q["merged"], 101)
        self.assertFalse(q["single_source"])
        self.assertEqual(q["agreement"][0]["ref_agreement"], 1.0)
        # The existing build reads the written file like any mirror file.
        deals = list(build_moj_market._read_rows(out / "moj/sales", "جدة"))
        new = [d for p, d in deals if p.name == "MOJ-Sales-2026-Q2.csv"]
        self.assertEqual(len(new), 101)
        self.assertEqual(new[0]["district"], "جده/ حي الروضة")
        self.assertEqual(rep["newest_deal"][:7], "2026-06")
        # The base tree is linked, not lost.
        self.assertTrue((out / "rega/quarterlies/rental/Rental-x-1st-Q-2026.csv").exists())

    def test_sources_that_disagree_stop_the_run(self):
        a = write(self.src / "raw.csv", fl.MOJ_HEADER, moj_rows(2026, 2, 100))
        b = write(self.src / "ksald.csv", KSALD_H, ksald_rows(2026, 2, 100, price=900000))
        with self.assertRaises(SystemExit):
            self.run_build(self.lock(self.overlay("raw", "2026-Q2", "moj", a),
                                     self.overlay("ksald", "2026-Q2", "ksald", b)))

    def test_checksum_mismatch_stops_the_run(self):
        b = write(self.src / "ksald.csv", KSALD_H, ksald_rows(2026, 2, 100))
        o = self.overlay("ksald", "2026-Q2", "ksald", b)
        o["sha256"] = "0" * 64
        with self.assertRaises(SystemExit):
            self.run_build(self.lock(o))

    def test_file_with_another_quarters_dates_is_rejected(self):
        b = write(self.src / "ksald.csv", KSALD_H, ksald_rows(2025, 2, 100))  # claims 2026-Q2, holds 2025-Q2
        out, rep = self.run_build(self.lock(self.overlay("ksald", "2026-Q2", "ksald", b)))
        self.assertEqual(rep["quarters"][0]["decision"], "no usable source")
        self.assertFalse((out / "moj/sales/MOJ-Sales-2026-Q2.csv").exists())

    def test_refs_already_in_another_quarter_are_dropped(self):
        rows = ksald_rows(2026, 2, 100)
        rows[0][-1] = "2026100000"  # a ref that the 2026-Q1 mirror file holds
        b = write(self.src / "ksald.csv", KSALD_H, rows)
        _, rep = self.run_build(self.lock(self.overlay("ksald", "2026-Q2", "ksald", b)))
        self.assertEqual(rep["quarters"][0]["dropped_cross_quarter_duplicates"], 1)
        self.assertEqual(rep["quarters"][0]["decision"], "wrote MOJ-Sales-2026-Q2.csv (99 deals)")

    def test_complete_base_file_wins(self):
        b = write(self.src / "ksald.csv", KSALD_H, ksald_rows(2026, 1, 100))
        out, rep = self.run_build(self.lock(self.overlay("ksald", "2026-Q1", "ksald", b)))
        self.assertTrue(rep["quarters"][0]["decision"].startswith("kept base file"))
        self.assertEqual(sha(out / "moj/sales/MOJ-Sales-2026-Q1.csv"), sha(self.base / "moj/sales/MOJ-Sales-2026-Q1.csv"))

    def test_partial_quarter_is_held_out_unless_accepted(self):
        b = write(self.src / "ksald.csv", KSALD_H, ksald_rows(2026, 2, 30))
        lock = self.lock(self.overlay("ksald", "2026-Q2", "ksald", b, preliminary_months=["2026-06"]))
        out, rep = self.run_build(lock)
        self.assertTrue(rep["quarters"][0]["decision"].startswith("held out: partial"))
        out, rep = self.run_build(lock, accept_partial=True)
        self.assertEqual(rep["quarters"][0]["preliminary_months"], ["2026-06"])
        self.assertTrue((out / "moj/sales/MOJ-Sales-2026-Q2.csv").exists())

    def test_writing_never_changes_the_base_through_a_hard_link(self):
        before = sha(self.base / "moj/sales/MOJ-Sales-2026-Q1.csv")
        b = write(self.src / "ksald.csv", KSALD_H, ksald_rows(2026, 1, 300))  # more deals: replaces the base file
        out, rep = self.run_build(self.lock(self.overlay("ksald", "2026-Q1", "ksald", b)))
        self.assertIn("replaces", rep["quarters"][0])
        self.assertEqual(sha(self.base / "moj/sales/MOJ-Sales-2026-Q1.csv"), before)


class ReportWindowTest(unittest.TestCase):
    def test_steps_back_over_a_missing_quarter(self):
        have = {f"{y}-Q{q}" for y in (2024, 2025, 2026) for q in (1, 2, 3, 4)} - {"2025-Q2", "2026-Q4"}
        self.assertEqual(build_report.full_windows("2026-Q3", have), "2026-Q1")
        self.assertEqual(build_report.full_windows("2026-Q3", have | {"2025-Q2"}), "2026-Q3")


if __name__ == "__main__":
    unittest.main()
