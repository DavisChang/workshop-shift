"""Local-only workshop scheduler. Python standard library, SQLite persistence."""
import argparse
import csv
import io
import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from scheduler import ROLES, generate

ROOT = Path(__file__).resolve().parent
DEFAULTS = {"needs": {"counter": 2, "technician": 3, "reception": 1}, "max_days": 5,
            "start_time": "09:00", "end_time": "18:00"}


def connect(path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as db, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY, name TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('counter','technician','reception')),
          active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)));
        CREATE TABLE IF NOT EXISTS leaves(id INTEGER PRIMARY KEY,
          employee_id INTEGER NOT NULL REFERENCES employees(id), start_date TEXT NOT NULL,
          end_date TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS assignments(employee_id INTEGER NOT NULL REFERENCES employees(id),
          date TEXT NOT NULL, PRIMARY KEY(employee_id,date));
        CREATE INDEX IF NOT EXISTS assignments_date ON assignments(date);
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS weeks(week TEXT PRIMARY KEY, generated_at TEXT NOT NULL);
        """)
        if not db.execute("SELECT 1 FROM settings").fetchone():
            db.execute("INSERT INTO settings VALUES(1,?)", (json.dumps(DEFAULTS),))
            for role, count in [("counter", 3), ("technician", 5), ("reception", 2)]:
                for i in range(count):
                    db.execute("INSERT INTO employees(name,role) VALUES(?,?)", (f"{ROLES[role]} {i+1:02}", role))


def valid_date(value):
    if not isinstance(value, str):
        raise ValueError("日期格式須為 YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("日期格式無效，請使用有效的 YYYY-MM-DD 日期") from None
    if parsed.isoformat() != value:
        raise ValueError("日期格式須為 YYYY-MM-DD")
    if not date(2000, 1, 3) <= parsed <= date(2099, 12, 27):
        raise ValueError("日期須介於 2000-01-03 至 2099-12-27")
    return parsed


def week_start(value):
    day = valid_date(value)
    return day - timedelta(days=day.weekday())


def settings_of(db):
    return json.loads(db.execute("SELECT value FROM settings WHERE id=1").fetchone()[0])


def rows(db, query, params=()):
    return [dict(r) for r in db.execute(query, params)]


def snapshot(db, monday):
    start, end = monday.isoformat(), (monday + timedelta(days=6)).isoformat()
    staff = rows(db, "SELECT * FROM employees ORDER BY id")
    leaves = rows(db, "SELECT * FROM leaves WHERE start_date<=? AND end_date>=? ORDER BY start_date,id", (end, start))
    shifts = rows(db, "SELECT * FROM assignments WHERE date BETWEEN ? AND ?", (start, end))
    config = settings_of(db)
    coverage = []
    for i in range(7):
        day = (monday + timedelta(days=i)).isoformat()
        for role in ROLES:
            ids = {e["id"] for e in staff if e["role"] == role}
            actual = sum(a["date"] == day and a["employee_id"] in ids for a in shifts)
            needed = config["needs"][role]
            coverage.append({"date": day, "role": role, "actual": actual, "needed": needed, "missing": max(0, needed-actual)})
    saved = db.execute("SELECT generated_at FROM weeks WHERE week=?", (start,)).fetchone()
    return {"week": start, "employees": staff, "leaves": leaves, "assignments": shifts,
            "settings": config, "coverage": coverage, "generated_at": saved[0] if saved else None, "roles": ROLES}


def employee(db, value):
    if type(value) is not int:
        raise ValueError("人員編號無效")
    person = db.execute("SELECT * FROM employees WHERE id=?", (value,)).fetchone()
    if not person:
        raise ValueError("找不到這位人員")
    return person


def mutate(db, path, body):
    if path == "/api/generate":
        monday = week_start(body["week"])
        state = snapshot(db, monday)
        history = {r[0]: r[1] for r in db.execute("SELECT employee_id,COUNT(*) FROM assignments WHERE date>=? AND date<? GROUP BY employee_id",
                    ((monday-timedelta(days=28)).isoformat(), monday.isoformat()))}
        # Preserve elapsed days when regenerating an existing plan.
        today = date.today().isoformat()
        existing = state["generated_at"] is not None or bool(state["assignments"])
        fixed = [a for a in state["assignments"] if a["date"] < today] if existing else []
        days = [(monday+timedelta(days=i)).isoformat() for i in range(7)]
        open_days = [d for d in days if not existing or d >= today]
        shifts = generate(state["employees"], state["leaves"], monday, state["settings"], history, fixed, open_days)
        db.execute("DELETE FROM assignments WHERE date BETWEEN ? AND ?", (monday.isoformat(), (monday+timedelta(days=6)).isoformat()))
        db.executemany("INSERT INTO assignments(employee_id,date) VALUES(:employee_id,:date)", shifts)
        db.execute("INSERT OR REPLACE INTO weeks VALUES(?,?)", (monday.isoformat(), datetime.now().isoformat(timespec="seconds")))
        missing = sum(c["missing"] for c in snapshot(db, monday)["coverage"])
        return {"message": f"已產生班表，尚有 {missing} 人次缺額" if missing else "已產生班表，七天人力全數到位", "assigned": len(shifts), "missing": missing}
    if path == "/api/employees":
        name, role = body.get("name", ""), body.get("role")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40 or role not in ROLES:
            raise ValueError("姓名須為 1–40 字，並選擇有效職務")
        if body.get("id") is None:
            db.execute("INSERT INTO employees(name,role) VALUES(?,?)", (name.strip(), role))
        else:
            old = employee(db, body["id"])
            active = body.get("active", bool(old["active"]))
            if type(active) is not bool:
                raise ValueError("在職狀態無效")
            if role != old["role"]:
                raise ValueError("既有人員職務不可變更；請停用後新增人員")
            db.execute("UPDATE employees SET name=?,active=? WHERE id=?", (name.strip(), int(active), old["id"]))
            if not active:
                db.execute("DELETE FROM assignments WHERE employee_id=? AND date>=?", (old["id"], date.today().isoformat()))
        return {"message": "人員資料已儲存"}
    if path == "/api/leaves":
        person = employee(db, body["employee_id"])
        if not person["active"]:
            raise ValueError("停用人員不能新增請假")
        start, end = valid_date(body["start_date"]), valid_date(body["end_date"])
        if end < start or (end-start).days > 365:
            raise ValueError("請假結束日須不早於開始日，且範圍不得超過 366 天")
        reason = body.get("reason", "")
        if not isinstance(reason, str) or len(reason) > 200:
            raise ValueError("原因不得超過 200 字")
        if db.execute("SELECT 1 FROM leaves WHERE employee_id=? AND start_date<=? AND end_date>=?", (person["id"], end.isoformat(), start.isoformat())).fetchone():
            raise ValueError("此人員已有重疊的請假紀錄")
        db.execute("INSERT INTO leaves(employee_id,start_date,end_date,reason) VALUES(?,?,?,?)", (person["id"], start.isoformat(), end.isoformat(), reason.strip()))
        removed = db.execute("DELETE FROM assignments WHERE employee_id=? AND date BETWEEN ? AND ?", (person["id"], start.isoformat(), end.isoformat())).rowcount
        return {"message": f"請假已登記，移除 {removed} 筆衝突班次；請查看缺額並重新排班"}
    if path == "/api/leaves/delete":
        if type(body.get("id")) is not int or not db.execute("DELETE FROM leaves WHERE id=?", (body["id"],)).rowcount:
            raise ValueError("找不到請假紀錄")
        return {"message": "已取消請假；可重新排班補入人員"}
    if path == "/api/settings":
        needs, limit = body.get("needs"), body.get("max_days")
        if not isinstance(needs, dict) or set(needs) != set(ROLES) or any(type(v) is not int or not 1 <= v <= 20 for v in needs.values()):
            raise ValueError("每個職務每日需求須為 1–20 人")
        if type(limit) is not int or not 1 <= limit <= 7:
            raise ValueError("每週上限須為 1–7 天")
        for key in ("start_time", "end_time"):
            value = body.get(key, "")
            if not isinstance(value, str) or len(value) != 5:
                raise ValueError("時間格式須為 HH:MM")
            try:
                if datetime.strptime(value, "%H:%M").strftime("%H:%M") != value:
                    raise ValueError()
            except ValueError:
                raise ValueError("時間格式須為有效的 HH:MM") from None
        if body["start_time"] >= body["end_time"]:
            raise ValueError("下班時間須晚於上班時間；目前支援當日單班")
        # Prevent existing schedules from violating a newly reduced weekly limit.
        counts = {}
        current_week = week_start(date.today().isoformat()).isoformat()
        for r in db.execute("SELECT employee_id,date FROM assignments WHERE date>=?", (current_week,)):
            key = (r[0], week_start(r[1]))
            counts[key] = counts.get(key, 0) + 1
        conflicts = [f"人員 #{key[0]}／{key[1]} 週" for key, count in counts.items() if count > limit]
        if conflicts:
            raise ValueError("已有班表超過此每週上限：" + "、".join(conflicts[:3]) + "；請先取消多餘班次")
        config = {k: body[k] for k in DEFAULTS}
        db.execute("UPDATE settings SET value=? WHERE id=1", (json.dumps(config),))
        return {"message": "規則已儲存，請檢查各週缺額並重新排班"}
    if path == "/api/assignment":
        person = employee(db, body["employee_id"])
        day = valid_date(body["date"])
        if type(body.get("working")) is not bool:
            raise ValueError("班次狀態無效")
        if not body["working"]:
            db.execute("DELETE FROM assignments WHERE employee_id=? AND date=?", (person["id"], day.isoformat()))
        else:
            if not person["active"]:
                raise ValueError("停用人員不可排班")
            if db.execute("SELECT 1 FROM leaves WHERE employee_id=? AND start_date<=? AND end_date>=?", (person["id"], day.isoformat(), day.isoformat())).fetchone():
                raise ValueError("當天已請假，不可排班")
            monday = week_start(day.isoformat())
            existing = db.execute("SELECT 1 FROM assignments WHERE employee_id=? AND date=?", (person["id"], day.isoformat())).fetchone()
            count = db.execute("SELECT COUNT(*) FROM assignments WHERE employee_id=? AND date BETWEEN ? AND ?", (person["id"], monday.isoformat(), (monday+timedelta(days=6)).isoformat())).fetchone()[0]
            if not existing and count >= settings_of(db)["max_days"]:
                raise ValueError("已達每週出勤上限")
            db.execute("INSERT OR IGNORE INTO assignments VALUES(?,?)", (person["id"], day.isoformat()))
        return {"message": "班次已更新"}
    raise ValueError("找不到此操作")


class Handler(BaseHTTPRequestHandler):
    def send(self, status, data, content_type="application/json; charset=utf-8", extra=None):
        payload = json.dumps(data, ensure_ascii=False).encode() if content_type.startswith("application/json") else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self):
        # Reject cross-origin writes and DNS rebinding against the local service.
        host = self.headers.get("Host", "")
        allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.server.server_port == 80:
            allowed_hosts.update(("127.0.0.1", "localhost"))
        if host not in allowed_hosts:
            self.send(403, {"error": "只允許本機連線"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + host:
            self.send(403, {"error": "拒絕跨來源請求"})
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        parsed = urlparse(self.path)
        if parsed.path in ("/api/state", "/api/export"):
            try:
                monday = week_start(parse_qs(parsed.query).get("week", [date.today().isoformat()])[0])
                with closing(connect(self.server.db_path)) as db, db:
                    db.execute("BEGIN")
                    state = snapshot(db, monday)
                if parsed.path == "/api/state":
                    self.send(200, state)
                else:
                    output = io.StringIO()
                    writer = csv.writer(output)
                    days = [(monday+timedelta(days=i)).isoformat() for i in range(7)]
                    writer.writerow(["人員", "職務"] + days + ["出勤天數"])
                    for e in state["employees"]:
                        shifts = {a["date"] for a in state["assignments"] if a["employee_id"] == e["id"]}
                        if not e["active"] and not shifts:
                            continue
                        name = e["name"]
                        if name.lstrip().startswith(("=", "+", "-", "@")) or name.startswith(("\t", "\r", "\n")):
                            name = "'" + name
                        writer.writerow([name, ROLES[e["role"]]] + [state["settings"]["start_time"]+"–"+state["settings"]["end_time"] if d in shifts else "請假" if any(l["employee_id"] == e["id"] and l["start_date"] <= d <= l["end_date"] for l in state["leaves"]) else "休息" for d in days] + [len(shifts)])
                    self.send(200, ("\ufeff"+output.getvalue()).encode(), "text/csv; charset=utf-8", {"Content-Disposition": f'attachment; filename="roster-{monday}.csv"'})
            except (ValueError, TypeError, OverflowError):
                self.send(400, {"error": "日期格式無效"})
            return
        files = {"/about/": ("../docs/index.html", "text/html"), "/about/style.css": ("../docs/style.css", "text/css"), "/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
        if parsed.path not in files:
            self.send(404, {"error": "找不到頁面"})
            return
        filename, mime = files[parsed.path]
        self.send(200, (ROOT / "static" / filename).read_bytes(), mime + "; charset=utf-8")

    def do_POST(self):
        if not self.allowed():
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.send(415, {"error": "請使用 JSON"})
            return
        try:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ValueError("請求內容長度無效") from None
            if not 0 < length <= 16384:
                raise ValueError("請求內容大小無效")
            try:
                body = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
                raise ValueError("JSON 格式無效或巢狀層級過深") from None
            if not isinstance(body, dict):
                raise ValueError("請求須為物件")
            with closing(connect(self.server.db_path)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                result = mutate(db, urlparse(self.path).path, body)
            self.send(200, result)
        except (ValueError, KeyError, TypeError, OverflowError, RecursionError, sqlite3.IntegrityError) as exc:
            self.send(400, {"error": str(exc) if isinstance(exc, ValueError) else "資料缺漏或格式錯誤"})
        except sqlite3.Error:
            self.send(500, {"error": "資料庫暫時無法寫入，請稍後再試"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=str(ROOT / "data" / "workshop.sqlite3"))
    args = parser.parse_args()
    initialize(args.db)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.db_path = args.db
    print(f"工作排班系統已啟動：http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
