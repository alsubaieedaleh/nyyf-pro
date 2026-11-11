"""Mock-portal tests for fetch_open_data.py: python -m unittest data/pipelines/tests/test_fetch_open_data.py"""

import csv
import http.server
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "fetch_open_data.py"
MOJ_H = ["المدينة", "الحي", "تاريخ الصفقة ميلادي", "السعر", "المساحة", "الرقم المرجعي"]
REGA_H = ["السنة", "الربع", "المنطقة", "المدينة", "الحي", "النوع", "الاستخدام", "عدد الصفقات", "مجموع قيم الصفقات", "مجموع المساحات"]
RENT_H = ["السنة", "الربع", "المنطقة", "المدينة", "الحي", "نوع العقار", "عدد الصفقات", "متوسط الايجار"]


def write(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def moj(y, q, n, seed):
    rnd = random.Random(seed)
    m0 = (q - 1) * 3 + 1
    return [["الرياض", "حي النرجس", f"{y}-{m0 + rnd.randint(0, 2):02d}-{rnd.randint(1, 28):02d}",
             rnd.randint(5, 9) * 100000, rnd.randint(300, 900), f"r{seed}-{i}"] for i in range(n)]


def rega(y, q, n):
    return [[y, q, "الجوف", "سكاكا", f"حي {i}", "أرض", "سكني", 5 + i, 1000000 + i, 2000 + i] for i in range(n)]


def rent(y, q, n):
    return [[y, q, "الرياض", "الرياض", f"حي {i}", "شقة", 10 + i, 20000 + i] for i in range(n)]


class FetchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        m = cls.tmp / "mirror"
        for q in (1, 3, 4):
            write(m / f"moj/sales/MOJ-Sales-2025-Q{q}.csv", MOJ_H, moj(2025, q, 100, q))
        write(m / "moj/sales/MOJ-Sales-2026-Q1.csv", MOJ_H, moj(2026, 1, 100, 5))
        write(m / "moj/sales/MOJ-Sales-2025-Q2.csv", MOJ_H, moj(2024, 2, 100, 9))  # misnamed, really 2024-Q2
        for i, nm in enumerate(["1st-Q-2025", "2nd-Q-2025", "3rd-Q-2025", "4th-Q-2025"]):
            write(m / f"rega/quarterlies/sales/Sales-transaction-indicators-in-AlJawf-{nm}.csv", REGA_H, rega(2025, i + 1, 50))
        write(m / "rega/quarterlies/sales/Sales-transaction-indicators-in-AlJawf-1st-Q-2026.csv", REGA_H, rega(2026, 1, 30))
        write(m / "rega/quarterlies/rental/Rental-indicators-in-Riyadh-region-1st-Q-2026.csv", RENT_H, rent(2026, 1, 50))

        files = {
            "D1": ("O/D1/v1/Transactions sale CSV.csv", MOJ_H, moj(2025, 2, 100, 7)),  # the real 2025-Q2
            "D2": ("O/D2/v1/Transactions sale CSV.csv", MOJ_H, moj(2026, 2, 100, 8)),
            "D3": ("O/D3/v1/Transactions sale CSV.csv", MOJ_H, moj(2026, 3, 30, 11)),  # partial
            "D4": ("O/D4/v1/Transactions sale CSV.csv", MOJ_H, moj(2026, 2, 100, 12)),  # second file for 2026-Q2
            "D5": ("O/D5/v1/Sales-transaction-indicators-in-AlJouf-Q1-2026.csv", REGA_H, rega(2026, 1, 50)),
            "D6": ("O/D6/v1/Rental-indicators-in-Riyadh-region-Q3-2026.csv", RENT_H, rent(2026, 1, 50)),  # Q1 rows
            "D7": ("O/D7/v1/Rental-indicators-in-Riyadh-region-Q2-2026.csv", RENT_H, rent(2026, 2, 20)),  # partial
        }
        for path, h, rows in files.values():
            write(cls.tmp / "portal" / path, h, rows)
        api = {
            "moj": [{"id": "D1", "titleAr": "صفقات البيع العقارية الربع الثاني 2025"},
                    {"id": "D2", "titleAr": "صفقات البيع العقارية الربع الثاني 2026"},
                    {"id": "D3", "titleAr": "صفقات البيع العقارية الربع الثالث 2026"},
                    {"id": "D4", "titleAr": "صفقات البيع العقارية الربع الثاني 2026 (نسخة)"}],
            "rega": [{"id": "D5", "titleAr": "مؤشرات صفقات البيع منطقة الجوف"},
                     {"id": "D6", "titleAr": "مؤشرات الإيجار منطقة الرياض"},
                     {"id": "D7", "titleAr": "مؤشرات الإيجار منطقة الرياض الربع الثاني"}],
        }
        root = cls.tmp / "portal"

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = urllib.parse.parse_qs(u.query)
                if u.path == "/data/api/organizations":
                    body = json.dumps({"datasets": api["moj" if "العدل" in q["organization"][0] else "rega"]}).encode()
                elif u.path.startswith("/api/datasets/"):
                    d = u.path.rsplit("/", 1)[-1]
                    body = json.dumps({"resources": [{"format": "CSV", "url": files[d][0]}]}).encode()
                elif u.path.startswith("/odp-public/"):
                    body = (root / urllib.parse.unquote(u.path[len("/odp-public/"):])).read_bytes()
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

        cls.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        def run(out, *extra):
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--mirror", str(m), "--out", str(out),
                 "--portal", f"http://127.0.0.1:{cls.server.server_port}", "--delay", "0", *extra],
                capture_output=True, text=True)

        cls.out = cls.tmp / "out"
        cls.proc = run(cls.out)
        cls.report = json.loads((cls.out / "fetch_report.json").read_text(encoding="utf-8"))["files"]
        cls.out_accept = cls.tmp / "out_accept"
        cls.proc_accept = run(cls.out_accept, "--accept-partial")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def entry(self, dataset_contains):
        return next(r for r in self.report if dataset_contains in r.get("dataset", "") or dataset_contains == r.get("portal_file"))

    def test_runs(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stdout + self.proc.stderr)

    def test_misnamed_moj_quarter_replaced(self):
        rows = (self.out / "moj/sales/MOJ-Sales-2025-Q2.csv").read_text(encoding="utf-8")
        self.assertIn("2025-0", rows)
        self.assertNotIn("2024-0", rows)
        self.assertIn("2024-0", (self.tmp / "mirror/moj/sales/MOJ-Sales-2025-Q2.csv").read_text(encoding="utf-8"))

    def test_partial_moj_quarter_held_out(self):  # audit R7-2
        self.assertFalse((self.out / "moj/sales/MOJ-Sales-2026-Q3.csv").exists())
        self.assertEqual(self.entry("الربع الثالث 2026")["flag"], "partial")

    def test_second_resource_same_quarter(self):  # audit R7-3
        self.assertEqual(self.entry("(نسخة)")["status"], "error")

    def test_rega_superset_under_another_name_replaces(self):  # audit R7-1
        sales = sorted(p.name for p in (self.out / "rega/quarterlies/sales").glob("*2026*"))
        self.assertEqual(sales, ["Sales-transaction-indicators-in-AlJouf-Q1-2026.csv"])
        self.assertEqual(self.entry("Sales-transaction-indicators-in-AlJouf-Q1-2026.csv")["status"], "replaced")
        self.assertTrue((self.tmp / "mirror/rega/quarterlies/sales/Sales-transaction-indicators-in-AlJawf-1st-Q-2026.csv").exists())

    def test_rega_rows_from_another_quarter_skipped(self):
        self.assertEqual(self.entry("Rental-indicators-in-Riyadh-region-Q3-2026.csv")["status"], "skipped")
        self.assertTrue((self.out / "rega/quarterlies/rental/Rental-indicators-in-Riyadh-region-1st-Q-2026.csv").exists())

    def test_partial_rent_quarter_held_out(self):  # audit R8
        self.assertFalse((self.out / "rega/quarterlies/rental/Rental-indicators-in-Riyadh-region-Q2-2026.csv").exists())
        e = self.entry("Rental-indicators-in-Riyadh-region-Q2-2026.csv")
        self.assertEqual((e["status"], e["flag"], e["completeness"]), ("skipped", "partial", 0.4))
        self.assertIn("ratio 0.40", self.proc.stdout)

    def test_accept_partial(self):  # audit R8 SHOULD
        self.assertEqual(self.proc_accept.returncode, 0, self.proc_accept.stdout + self.proc_accept.stderr)
        self.assertTrue((self.out_accept / "moj/sales/MOJ-Sales-2026-Q3.csv").exists())
        self.assertTrue((self.out_accept / "rega/quarterlies/rental/Rental-indicators-in-Riyadh-region-Q2-2026.csv").exists())

    def test_series_key(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import fetch_open_data as f
        self.assertEqual(f.series_key("MOJ-Sales-2025-Q2.csv"), f.series_key("MOJ-Sales-2026-Q1.csv"))
        self.assertEqual(f.series_key("Sales-transaction-indicators-in-Riyadh-Q1-2026.csv"),
                         f.series_key("Sales-transaction-indicators-in-Riyadh-3rdQ-2024.csv"))


if __name__ == "__main__":
    unittest.main()
