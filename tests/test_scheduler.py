"""排班核心 scheduler.generate 的驗收測試（標準函式庫 unittest）。

執行：在 repo 根目錄 `python -m unittest tests/test_scheduler.py -v`
"""
import sys
import unittest
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import generate  # noqa: E402

MONDAY = date(2026, 9, 7)  # 2026-09-07 是星期一
NEEDS = {"counter": 2, "technician": 3, "reception": 1}
SETTINGS = {"max_days": 5, "needs": NEEDS}


def days_from(monday):
    return [(monday + timedelta(days=i)).isoformat() for i in range(7)]


DAYS = days_from(MONDAY)


def staff(counter=3, technician=5, reception=2):
    """預設 10 人：櫃檯 3、技師 5、接待 2（容量 15/25/10 ≥ 需求 14/21/7）。"""
    people = []
    for role, count in (("counter", counter), ("technician", technician), ("reception", reception)):
        people.extend({"id": f"{role}{k}", "role": role, "active": True} for k in range(count))
    return people


def leave(employee_id, start, end=None):
    return {"employee_id": employee_id, "start_date": start, "end_date": end or start}


def per_day_role(assignments, employees):
    """(date, role) -> 班數；未知 employee_id 會 KeyError，視為失敗。"""
    role_of = {e["id"]: e["role"] for e in employees}
    return Counter((a["date"], role_of[a["employee_id"]]) for a in assignments)


def per_person(assignments):
    return Counter(a["employee_id"] for a in assignments)


def monday_with_rotation_zero():
    """讓 index 0 的員工最便宜的日子落在星期一（rotation == 0）。"""
    m = MONDAY
    while (m.toordinal() // 7) % 7:
        m += timedelta(days=7)
    return m


class SchedulerTests(unittest.TestCase):
    def assert_full_coverage(self, assignments, employees, needs=NEEDS, days=DAYS):
        counts = per_day_role(assignments, employees)
        for day in days:
            for role, need in needs.items():
                self.assertEqual(counts[(day, role)], need, f"{day} {role}")

    # 1. 10 人預設 2/3/1 → 42 班且每天全覆蓋
    def test_default_ten_people_produce_42_shifts_full_coverage(self):
        employees = staff()
        result = generate(employees, [], MONDAY, SETTINGS)
        self.assertEqual(len(result), 42)
        self.assert_full_coverage(result, employees)
        self.assertEqual(len({(a["employee_id"], a["date"]) for a in result}), 42, "同一人同一天不得重複")

    # 2. 每人每週最多 5 天
    def test_each_person_at_most_five_days(self):
        result = generate(staff(), [], MONDAY, SETTINGS)
        for pid, n in per_person(result).items():
            self.assertLessEqual(n, 5, pid)

    # 3. 同輸入結果穩定
    def test_same_input_is_deterministic(self):
        employees = staff()
        leaves = [leave("technician1", DAYS[2], DAYS[3])]
        history = {"counter0": 4, "technician2": 1}
        first = generate(employees, leaves, MONDAY, SETTINGS, history)
        second = generate(employees, leaves, MONDAY, SETTINGS, history)
        self.assertEqual(first, second)

    # 4. 請假日排除
    def test_leave_day_is_excluded(self):
        employees = staff()
        result = generate(employees, [leave("technician0", DAYS[1])], MONDAY, SETTINGS)
        self.assertNotIn(("technician0", DAYS[1]), {(a["employee_id"], a["date"]) for a in result})
        self.assert_full_coverage(result, employees)  # 技師 5 人少一人一天仍可全覆蓋

    # 5. 全職務人員請假 → 保留缺額，不由其他職務填補
    def test_all_role_staff_on_leave_keeps_shortfall(self):
        employees = staff()
        leaves = [leave("reception0", DAYS[2]), leave("reception1", DAYS[2])]
        result = generate(employees, leaves, MONDAY, SETTINGS)
        counts = per_day_role(result, employees)
        self.assertEqual(counts[(DAYS[2], "reception")], 0)
        self.assertEqual(len(result), 41)
        for day in DAYS:
            self.assertEqual(counts[(day, "counter")], 2, day)
            self.assertEqual(counts[(day, "technician")], 3, day)
            if day != DAYS[2]:
                self.assertEqual(counts[(day, "reception")], 1, day)

    # 6. 停用人員不排
    def test_inactive_employee_is_not_scheduled(self):
        employees = staff()
        employees[0]["active"] = False  # counter0 停用 → 櫃檯剩 2 人，容量 10 < 需求 14
        result = generate(employees, [], MONDAY, SETTINGS)
        self.assertNotIn("counter0", per_person(result))
        self.assertEqual(sum(1 for a in result if a["employee_id"].startswith("counter")), 10)

    # 7. 單人無法滿足每日 2 名，不能重複出勤
    def test_single_person_cannot_double_up(self):
        employees = staff(counter=1, technician=0, reception=0)
        needs = {"counter": 2, "technician": 0, "reception": 0}
        result = generate(employees, [], MONDAY, {"max_days": 5, "needs": needs})
        pairs = Counter((a["employee_id"], a["date"]) for a in result)
        self.assertTrue(all(n == 1 for n in pairs.values()), pairs)
        self.assertEqual(len(result), 5)  # 受 max_days 限制
        self.assertLessEqual(max(per_day_role(result, employees).values()), 1)

    # 8. 不同 max_days
    def test_max_days_three_caps_and_reduces_total(self):
        employees = staff()
        result = generate(employees, [], MONDAY, {"max_days": 3, "needs": NEEDS})
        self.assertTrue(all(n <= 3 for n in per_person(result).values()))
        self.assertEqual(len(result), 30)  # 9 + 15 + 6
        counts = per_day_role(result, employees)
        for (day, role), n in counts.items():
            self.assertLessEqual(n, NEEDS[role], (day, role))

    def test_max_days_seven_still_full_coverage(self):
        employees = staff()
        result = generate(employees, [], MONDAY, {"max_days": 7, "needs": NEEDS})
        self.assertEqual(len(result), 42)
        self.assert_full_coverage(result, employees)
        self.assertTrue(all(n <= 7 for n in per_person(result).values()))

    # 9. constrained availability：需經反向邊重排才能全覆蓋
    def test_constrained_availability_requires_reverse_edge_rerouting(self):
        monday = monday_with_rotation_zero()
        days = days_from(monday)
        employees = staff(counter=2, technician=0, reception=0)
        # A（index 0）最便宜是星期一且可 Mon/Tue；B 只可 Mon。
        # 貪婪會先把 A 放 Mon，B 就沒位子；正確解是 B→Mon、A→Tue。
        leaves = [leave("counter0", days[2], days[6]), leave("counter1", days[1], days[6])]
        needs = {"counter": 1, "technician": 0, "reception": 0}
        result = generate(employees, leaves, monday, {"max_days": 1, "needs": needs})
        self.assertEqual({(a["employee_id"], a["date"]) for a in result},
                         {("counter1", days[0]), ("counter0", days[1])})

    # 10. 跨週請假含邊界（start/end 皆含）
    def test_cross_week_leave_boundaries_inclusive(self):
        employees = staff(counter=0, technician=0, reception=1)
        prev_sat = (MONDAY - timedelta(days=2)).isoformat()
        next_wed = (MONDAY + timedelta(days=9)).isoformat()
        leaves = [leave("reception0", prev_sat, DAYS[0]), leave("reception0", DAYS[6], next_wed)]
        needs = {"counter": 0, "technician": 0, "reception": 1}
        result = generate(employees, leaves, MONDAY, {"max_days": 7, "needs": needs})
        self.assertEqual(sorted(a["date"] for a in result), DAYS[1:6])  # Tue..Sat

    # 11. 櫃檯一人請 2 天假仍全覆蓋：剩 5 天可用不會壓低 5 天上限
    def test_counter_two_day_leave_still_full_coverage(self):
        employees = staff()
        result = generate(employees, [leave("counter0", DAYS[2], DAYS[3])], MONDAY, SETTINGS)
        self.assertEqual(len(result), 42)
        self.assert_full_coverage(result, employees)
        own = {a["date"] for a in result if a["employee_id"] == "counter0"}
        self.assertTrue(own.isdisjoint({DAYS[2], DAYS[3]}))
        self.assertIn(len(own), (4, 5))  # 14 班 / 3 人 = 5+5+4，請假者的 5 天可用天數足以承擔任一份


if __name__ == "__main__":
    unittest.main()
