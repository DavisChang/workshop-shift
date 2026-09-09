import copy
import tempfile
import unittest
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from app import DEFAULTS, connect, initialize, mutate, snapshot, valid_date, week_start


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        initialize(self.path)
        self.db = connect(self.path)
        self.monday = week_start(date.today().isoformat()) + timedelta(days=7)
        self.week = self.monday.isoformat()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def call(self, path, body):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            return mutate(self.db, path, body)

    def state(self, monday=None):
        return snapshot(self.db, monday or self.monday)

    def generate(self, week=None):
        return self.call("/api/generate", {"week": week or self.week})

    def test_seed_exactly_ten_and_idempotent(self):
        initialize(self.path)
        state = self.state()
        self.assertEqual(Counter(e["role"] for e in state["employees"]), {"counter": 3, "technician": 5, "reception": 2})
        self.assertEqual(state["settings"], DEFAULTS)

    def test_initialization_releases_database_handle(self):
        opened = []

        def tracked(path):
            db = connect(path)
            opened.append(db)
            return db

        with patch("app.connect", side_effect=tracked):
            initialize(self.path)
        self.assertEqual(len(opened), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            opened[0].execute("SELECT 1")

    def test_generate_persist_reconnect_and_idempotence(self):
        self.assertEqual(self.generate()["missing"], 0)
        before = self.state()
        self.assertEqual(len(before["assignments"]), 42)
        self.generate()
        self.assertEqual(self.state()["assignments"], before["assignments"])
        with closing(connect(self.path)) as other, other:
            self.assertEqual(snapshot(other, self.monday)["assignments"], before["assignments"])

    def test_leave_removes_shift_and_regeneration_excludes_it(self):
        self.generate()
        shift = self.state()["assignments"][0]
        result = self.call("/api/leaves", {"employee_id": shift["employee_id"], "start_date": shift["date"], "end_date": shift["date"]})
        self.assertIn("移除 1 筆", result["message"])
        self.assertNotIn(shift, self.state()["assignments"])
        self.assertEqual(sum(c["missing"] for c in self.state()["coverage"]), 1)
        self.generate()
        self.assertNotIn(shift, self.state()["assignments"])
        self.assertEqual(sum(c["missing"] for c in self.state()["coverage"]), 0)

    def test_infeasible_day_reports_real_shortfall(self):
        for pid in (1, 2, 3):
            self.call("/api/leaves", {"employee_id": pid, "start_date": self.week, "end_date": self.week})
        result = self.generate()
        self.assertEqual(result["assigned"], 40)
        self.assertEqual(result["missing"], 2)
        self.assertEqual(next(c for c in self.state()["coverage"] if c["role"] == "counter" and c["date"] == self.week)["actual"], 0)

    def test_overlapping_leave_rejected_and_transaction_unchanged(self):
        body = {"employee_id": 1, "start_date": self.week, "end_date": (self.monday+timedelta(days=2)).isoformat()}
        self.call("/api/leaves", body)
        before = self.state()
        with self.assertRaisesRegex(ValueError, "重疊"):
            self.call("/api/leaves", dict(body, start_date=body["end_date"]))
        self.assertEqual(self.state(), before)

    def test_cross_week_leave_removes_assignments_in_both_weeks(self):
        next_week = self.monday+timedelta(days=7)
        self.generate()
        self.generate(next_week.isoformat())
        self.call("/api/leaves", {"employee_id": 1, "start_date": (self.monday+timedelta(days=5)).isoformat(), "end_date": (self.monday+timedelta(days=8)).isoformat()})
        for monday in (self.monday, next_week):
            state = self.state(monday)
            self.assertEqual(len(state["leaves"]), 1)
            for a in state["assignments"]:
                self.assertFalse(a["employee_id"] == 1 and (self.monday+timedelta(days=5)).isoformat() <= a["date"] <= (self.monday+timedelta(days=8)).isoformat())

    def test_manual_assignment_on_leave_is_rejected(self):
        self.call("/api/leaves", {"employee_id": 1, "start_date": self.week, "end_date": self.week})
        with self.assertRaisesRegex(ValueError, "請假"):
            self.call("/api/assignment", {"employee_id": 1, "date": self.week, "working": True})

    def test_sixth_shift_rejected_and_repeat_add_is_idempotent(self):
        for i in range(5):
            self.call("/api/assignment", {"employee_id": 1, "date": (self.monday+timedelta(days=i)).isoformat(), "working": True})
        self.call("/api/assignment", {"employee_id": 1, "date": self.week, "working": True})
        with self.assertRaisesRegex(ValueError, "上限"):
            self.call("/api/assignment", {"employee_id": 1, "date": (self.monday+timedelta(days=5)).isoformat(), "working": True})
        self.assertEqual(len(self.state()["assignments"]), 5)

    def test_cancel_leave_makes_employee_available(self):
        for pid in (9, 10):
            self.call("/api/leaves", {"employee_id": pid, "start_date": self.week, "end_date": self.week})
        self.assertEqual(self.generate()["missing"], 1)
        self.call("/api/leaves/delete", {"id": self.state()["leaves"][0]["id"]})
        self.assertEqual(self.generate()["missing"], 0)

    def test_disabled_employee_name_edit_does_not_reactivate(self):
        self.call("/api/employees", {"id": 1, "name": "櫃檯 01", "role": "counter", "active": False})
        self.call("/api/employees", {"id": 1, "name": "新的姓名", "role": "counter"})
        self.assertEqual(self.state()["employees"][0]["active"], 0)
        self.generate()
        self.assertFalse(any(a["employee_id"] == 1 for a in self.state()["assignments"]))

    def test_disable_preserves_historical_coverage(self):
        past = self.monday-timedelta(days=21)
        self.generate(past.isoformat())
        old = self.state(past)
        self.generate()
        self.call("/api/employees", {"id": 1, "name": "櫃檯 01", "role": "counter", "active": False})
        self.assertEqual(self.state(past)["coverage"], old["coverage"])
        self.assertEqual(self.state(past)["assignments"], old["assignments"])
        self.assertFalse(any(a["employee_id"] == 1 for a in self.state()["assignments"]))

    def test_regeneration_preserves_elapsed_days(self):
        past = self.monday-timedelta(days=21)
        self.generate(past.isoformat())
        shift = self.state(past)["assignments"][0]
        self.call("/api/assignment", dict(shift, working=False))
        before = self.state(past)["assignments"]
        self.generate(past.isoformat())
        self.assertEqual(self.state(past)["assignments"], before)

    def test_regeneration_current_week_counts_frozen_shifts(self):
        current = self.monday-timedelta(days=7)
        self.generate(current.isoformat())
        old = [a for a in self.state(current)["assignments"] if a["date"] < date.today().isoformat()]
        self.generate(current.isoformat())
        new = self.state(current)["assignments"]
        self.assertEqual([a for a in new if a["date"] < date.today().isoformat()], old)
        self.assertLessEqual(max(Counter(a["employee_id"] for a in new).values()), 5)
        self.assertTrue(all(c["missing"] == 0 for c in self.state(current)["coverage"]))

    def test_generation_does_not_change_other_weeks(self):
        self.generate()
        before = self.state()["assignments"]
        self.generate((self.monday+timedelta(days=7)).isoformat())
        self.assertEqual(self.state()["assignments"], before)

    def test_settings_update_and_shortfall_recalculation(self):
        self.generate()
        new = copy.deepcopy(DEFAULTS)
        new["needs"]["counter"] = 3
        self.call("/api/settings", new)
        self.assertEqual(sum(c["missing"] for c in self.state()["coverage"]), 7)
        self.assertEqual(self.generate()["missing"], 6)

    def test_settings_reject_existing_future_overlimit(self):
        self.generate()
        with self.assertRaisesRegex(ValueError, "人員 #"):
            self.call("/api/settings", dict(DEFAULTS, max_days=4))
        self.assertEqual(self.state()["settings"]["max_days"], 5)

    def test_historical_shifts_do_not_block_new_lower_limit(self):
        self.generate((self.monday-timedelta(days=21)).isoformat())
        self.call("/api/settings", dict(DEFAULTS, max_days=4))
        self.assertEqual(self.state()["settings"]["max_days"], 4)

    def test_invalid_inputs_leave_database_unchanged(self):
        examples = [
            ("/api/employees", {"name": "", "role": "counter"}),
            ("/api/employees", {"name": "a", "role": "pilot"}),
            ("/api/employees", {"id": 1, "name": "a", "role": "technician"}),
            ("/api/settings", dict(DEFAULTS, max_days=True)),
            ("/api/settings", dict(DEFAULTS, end_time="08:00")),
            ("/api/settings", dict(DEFAULTS, needs={"counter": 2})),
            ("/api/leaves", {"employee_id": 1, "start_date": self.week, "end_date": "2001-01-01"}),
            ("/api/leaves", {"employee_id": 999, "start_date": self.week, "end_date": self.week}),
            ("/api/assignment", {"employee_id": 1, "date": self.week, "working": "false"}),
        ]
        before = self.state()
        for path, body in examples:
            with self.subTest(path=path, body=body), self.assertRaises(ValueError):
                self.call(path, body)
            self.assertEqual(self.state(), before)

    def test_extreme_dates_rejected(self):
        for value in ("9999-12-31", "0001-01-05", "2026-02-30", "2026-1-01", "2099-12-31", "2000-01-01", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                valid_date(value)

    def test_last_supported_week_can_be_edited_and_settings_saved(self):
        self.generate("2099-12-27")
        final = self.state(week_start("2099-12-27"))
        self.assertEqual(len(final["assignments"]), 42)
        self.assertLessEqual(max(a["date"] for a in final["assignments"]), "2099-12-27")
        self.call("/api/settings", DEFAULTS)
        self.call("/api/assignment", dict(final["assignments"][0], working=False))

    def test_fixed_days_leave_five_day_limit_capacity_for_remaining_days(self):
        from scheduler import generate
        staff = self.state()["employees"]
        fixed = [{"employee_id": 1, "date": (self.monday+timedelta(days=i)).isoformat()} for i in range(3)]
        open_days = [(self.monday+timedelta(days=i)).isoformat() for i in range(3, 7)]
        result = generate(staff, [], self.monday, DEFAULTS, fixed=fixed, open_days=open_days)
        self.assertTrue(all(a in result for a in fixed))
        self.assertEqual([a for a in result if a["date"] < open_days[0]], fixed)
        self.assertLessEqual(sum(a["employee_id"] == 1 for a in result), 5)
        self.assertEqual(len(result), 27)  # 三筆保留 + 未來四日每天六人


if __name__ == "__main__":
    unittest.main()
