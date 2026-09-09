import csv
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app import Handler, initialize, week_start


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / "http.sqlite3"
        initialize(db_path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.server.db_path = db_path
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.week = (week_start(date.today().isoformat())+timedelta(days=7)).isoformat()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, body=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        payload = json.dumps(body) if body is not None else raw
        request_headers = {"Content-Type": "application/json"} if payload is not None else {}
        request_headers.update(headers or {})
        connection.request("POST" if payload is not None else "GET", path, payload, request_headers)
        response = connection.getresponse()
        data = response.read()
        result = (response.status, dict(response.getheaders()), data)
        connection.close()
        return result

    def json(self, path, body=None):
        status, _, data = self.request(path, body)
        self.assertEqual(status, 200, data)
        return json.loads(data)

    def state(self):
        return self.json("/api/state?week="+self.week)

    def test_static_pages_and_security_headers(self):
        for path, content_type in (("/", "text/html"), ("/app.js", "text/javascript"), ("/style.css", "text/css")):
            status, headers, data = self.request(path)
            self.assertEqual(status, 200)
            self.assertTrue(headers["Content-Type"].startswith(content_type))
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
            self.assertGreater(len(data), 200)
        self.assertEqual(self.request("/../../app.py")[0], 404)
        self.assertEqual(self.request("/data/workshop.sqlite3")[0], 404)

    def test_api_releases_database_handles_after_read_and_write(self):
        opened = []

        def tracked(path):
            # The check is performed after requests finish on the main test thread.
            db = sqlite3.connect(path, timeout=15, check_same_thread=False)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            opened.append(db)
            return db

        with patch("app.connect", side_effect=tracked):
            self.state()
            self.json("/api/generate", {"week": self.week})
        self.assertEqual(len(opened), 2)
        for db in opened:
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute("SELECT 1")

    def test_full_leave_reschedule_export_workflow(self):
        self.assertEqual(self.json("/api/generate", {"week": self.week})["missing"], 0)
        initial = self.state()
        self.assertEqual(len(initial["employees"]), 10)
        shift = initial["assignments"][0]
        self.json("/api/leaves", {"employee_id": shift["employee_id"], "start_date": shift["date"], "end_date": shift["date"], "reason": "驗收測試"})
        self.assertEqual(sum(c["missing"] for c in self.state()["coverage"]), 1)
        self.assertEqual(self.json("/api/generate", {"week": self.week})["missing"], 0)
        status, headers, data = self.request("/api/export?week="+self.week)
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        table = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(len(table), 11)
        self.assertTrue(all(len(row) == 10 for row in table))
        self.assertEqual(sum(int(row[-1]) for row in table[1:]), 42)
        self.assertIn("請假", data.decode("utf-8-sig"))

    def test_cross_origin_and_invalid_host_rejected(self):
        self.assertEqual(self.request("/api/generate", {"week": self.week}, {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request("/api/state", headers={"Host": "evil.example"})[0], 403)
        origin = f"http://127.0.0.1:{self.server.server_port}"
        self.assertEqual(self.request("/api/generate", {"week": self.week}, {"Origin": origin})[0], 200)

    def test_malformed_requests_return_errors_without_mutation(self):
        before = self.state()
        for raw in ("{bad", "[]", "null", "[" * 3000):
            self.assertEqual(self.request("/api/leaves", raw=raw)[0], 400)
        self.assertEqual(self.request("/api/leaves", raw="{}", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("/api/generate", {"week": "0001-01-05"})[0], 400)
        self.assertEqual(self.request("/api/state?week=9999-12-31")[0], 400)
        self.assertEqual(self.request("/api/no-such-route", {})[0], 400)
        self.assertEqual(self.state(), before)

    def test_csv_formula_injection_escaped_and_unicode_preserved(self):
        self.json("/api/employees", {"id": 1, "name": '=HYPERLINK("https://evil.example")', "role": "counter"})
        _, _, data = self.request("/api/export?week="+self.week)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        table = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertTrue(table[1][0].startswith("'="))
        self.assertEqual(table[1][1], "櫃檯")

    def test_concurrent_leave_and_generation_never_schedule_absent_person(self):
        leave = {"employee_id": 1, "start_date": self.week, "end_date": self.week}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.request, "/api/generate", {"week": self.week}), pool.submit(self.request, "/api/leaves", leave)]
            for future in futures:
                self.assertEqual(future.result()[0], 200)
        state = self.state()
        self.assertEqual(len(state["leaves"]), 1)
        self.assertNotIn({"employee_id": 1, "date": self.week}, state["assignments"])

    def test_concurrent_identical_leaves_only_one_succeeds(self):
        leave = {"employee_id": 1, "start_date": self.week, "end_date": self.week}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.request, "/api/leaves", leave) for _ in range(2)]
            codes = sorted(f.result()[0] for f in futures)
        self.assertEqual(codes, [200, 400])
        self.assertEqual(len(self.state()["leaves"]), 1)


if __name__ == "__main__":
    unittest.main()
