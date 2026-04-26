import sqlite3
import json
from datetime import date, timedelta, datetime

DB = "diary.db"


def init_db():
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id      INTEGER UNIQUE NOT NULL,
                username   TEXT,
                first_name TEXT,
                tz_offset  INTEGER DEFAULT 5,   -- UTC+5 Пермь по умолчанию
                created_at TEXT DEFAULT (date('now'))
            );

            CREATE TABLE IF NOT EXISTS entries (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                date          TEXT NOT NULL,
                -- утро
                sleep_min     INTEGER,           -- минуты сна (например 450 = 7ч 30мин)
                sleep_q       INTEGER,
                dreams        INTEGER,
                phone_morning INTEGER,
                -- вечер
                mood          INTEGER,
                energy        INTEGER,
                sport         INTEGER,
                water         INTEGER,
                food_ok       INTEGER,
                meditation    INTEGER,
                reading       INTEGER,
                social        INTEGER,
                note          TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS plans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                date        TEXT NOT NULL,
                subject     TEXT NOT NULL,
                task_type   TEXT,
                done        INTEGER DEFAULT 0,
                is_custom   INTEGER DEFAULT 0,  -- 1 = своя задача
                remind_at   TEXT,               -- '14:30' или NULL
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS ege_settings (
                user_id     INTEGER PRIMARY KEY,
                subjects    TEXT,               -- JSON: ["russian","math","informatics"]
                schedule    TEXT,               -- JSON: {"Mon":["russian"],"Tue":["math"],...}
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS ege_tasks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                date         TEXT NOT NULL,
                subject      TEXT NOT NULL,
                task_type    TEXT NOT NULL,      -- new/repeat/trial/errors
                task_number  INTEGER,            -- номер задания (для new)
                done         INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS ege_progress (
                user_id      INTEGER NOT NULL,
                subject      TEXT NOT NULL,
                task_number  INTEGER NOT NULL,
                times_done   INTEGER DEFAULT 0,
                last_done    TEXT,
                PRIMARY KEY (user_id, subject, task_number)
            );
        """)


# ── users ─────────────────────────────────────────────────

def upsert_user(tg_id: int, username: str, first_name: str) -> int:
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE tg_id=?", (tg_id,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE users SET username=?, first_name=? WHERE tg_id=?",
                      (username, first_name, tg_id))
            return row[0]
        c.execute("INSERT INTO users (tg_id, username, first_name) VALUES (?,?,?)",
                  (tg_id, username, first_name))
        return c.lastrowid


def get_uid(tg_id: int) -> int | None:
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE tg_id=?", (tg_id,))
        row = c.fetchone()
        return row[0] if row else None


def get_user_tz(tg_id: int) -> int:
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT tz_offset FROM users WHERE tg_id=?", (tg_id,))
        row = c.fetchone()
        return row[0] if row else 5


def set_user_tz(tg_id: int, tz_offset: int):
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET tz_offset=? WHERE tg_id=?", (tz_offset, tg_id))


def all_users() -> list[dict]:
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT tg_id, first_name, tz_offset FROM users")
        return [dict(r) for r in c.fetchall()]


# ── entries ───────────────────────────────────────────────

def save_morning(user_id: int, data: dict):
    if not user_id:
        return
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM entries WHERE user_id=? AND date=?", (user_id, today))
        row = c.fetchone()
        if row:
            c.execute("""UPDATE entries SET sleep_min=?, sleep_q=?, dreams=?, phone_morning=?
                         WHERE id=?""",
                      (data.get("sleep_min"), data.get("sleep_q"),
                       data.get("dreams"), data.get("phone_morning"), row[0]))
        else:
            c.execute("""INSERT INTO entries (user_id, date, sleep_min, sleep_q, dreams, phone_morning)
                         VALUES (?,?,?,?,?,?)""",
                      (user_id, today, data.get("sleep_min"), data.get("sleep_q"),
                       data.get("dreams"), data.get("phone_morning")))
        conn.commit()


def save_evening(user_id: int, data: dict):
    if not user_id:
        return
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM entries WHERE user_id=? AND date=?", (user_id, today))
        row = c.fetchone()
        fields = ("mood", "energy", "sport", "water", "food_ok",
                  "meditation", "reading", "social", "note")
        vals = [data.get(f) for f in fields]
        if row:
            sets = ", ".join(f"{f}=?" for f in fields)
            c.execute(f"UPDATE entries SET {sets} WHERE id=?", vals + [row[0]])
        else:
            cols = "user_id, date, " + ", ".join(fields)
            ph = ", ".join(["?"] * (2 + len(fields)))
            c.execute(f"INSERT INTO entries ({cols}) VALUES ({ph})",
                      [user_id, today] + vals)
        conn.commit()


def get_week_stats(user_id: int) -> dict:
    today = date.today()
    week_ago = str(today - timedelta(days=6))
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""SELECT * FROM entries WHERE user_id=? AND date BETWEEN ? AND ?
                     ORDER BY date""", (user_id, week_ago, str(today)))
        rows = [dict(r) for r in c.fetchall()]

    if not rows:
        return {}

    def avg(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def pct(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals) * 100) if vals else None

    def fmt_sleep(mins):
        if not mins:
            return None
        h = mins // 60
        m = mins % 60
        return f"{h}ч {m}мин" if m else f"{h}ч"

    dow_names = {"Mon":"Пн","Tue":"Вт","Wed":"Ср","Thu":"Чт","Fri":"Пт","Sat":"Сб","Sun":"Вс"}
    mood_by_dow = {}
    for r in rows:
        if r.get("mood"):
            dow = date.fromisoformat(r["date"]).strftime("%a")
            mood_by_dow[dow_names.get(dow, dow)] = r["mood"]

    # Сон в часах для корреляций
    sleep_hours = [(r["sleep_min"] / 60) if r.get("sleep_min") else None for r in rows]

    insights = []
    good = [rows[i]["mood"] for i, h in enumerate(sleep_hours) if h and h >= 7 and rows[i].get("mood")]
    bad  = [rows[i]["mood"] for i, h in enumerate(sleep_hours) if h and h < 7 and rows[i].get("mood")]
    if good and bad:
        diff = round(sum(good)/len(good) - sum(bad)/len(bad), 1)
        if diff > 0.2:
            insights.append(f"😴 Когда спишь 7+ часов — настроение выше на {diff} балла")

    sp = [r["mood"] for r in rows if r.get("sport") == 1 and r.get("mood")]
    nsp= [r["mood"] for r in rows if r.get("sport") == 0 and r.get("mood")]
    if sp and nsp:
        insights.append(
            f"🏃 Спорт → настроение {round(sum(sp)/len(sp),1)} "
            f"vs {round(sum(nsp)/len(nsp),1)} без него"
        )

    ph = [r for r in rows if r.get("phone_morning") is not None]
    ph_bad = [r for r in ph if r["phone_morning"] == 1]
    if ph:
        p = round(len(ph_bad)/len(ph)*100)
        if p > 50:
            insights.append(f"📱 Телефон утром снижает твою продуктивность — {p}% дней этой недели")

    # Средний сон в минутах и часах
    sleep_mins_list = [r["sleep_min"] for r in rows if r.get("sleep_min")]
    avg_sleep_min = round(sum(sleep_mins_list)/len(sleep_mins_list)) if sleep_mins_list else None

    return {
        "days": len(rows),
        "avg_mood": avg("mood"),
        "avg_sleep_min": avg_sleep_min,
        "avg_sleep_fmt": fmt_sleep(avg_sleep_min),
        "avg_sleep_q": avg("sleep_q"),
        "avg_energy": avg("energy"),
        "sport_pct": pct("sport"),
        "meditation_pct": pct("meditation"),
        "reading_pct": pct("reading"),
        "social_pct": pct("social"),
        "water_avg": avg("water"),
        "mood_by_dow": mood_by_dow,
        "insights": insights,
        "raw": rows,   # для AI-анализа
    }


# ── plans ─────────────────────────────────────────────────

def save_plan(user_id: int, subject: str, task_type: str,
              is_custom: int = 0, remind_at: str = None):
    if not user_id or not subject:
        return
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        if not is_custom:
            c.execute("SELECT id FROM plans WHERE user_id=? AND date=? AND subject=?",
                      (user_id, today, subject))
            row = c.fetchone()
            if row:
                c.execute("UPDATE plans SET task_type=?, done=0 WHERE id=?", (task_type, row[0]))
                conn.commit()
                return
        c.execute("""INSERT INTO plans (user_id, date, subject, task_type, is_custom, remind_at)
                     VALUES (?,?,?,?,?,?)""",
                  (user_id, today, subject, task_type, is_custom, remind_at))
        conn.commit()


def get_today_plans(user_id: int) -> list[dict]:
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM plans WHERE user_id=? AND date=? ORDER BY id",
                  (user_id, today))
        return [dict(r) for r in c.fetchall()]


def toggle_plan(plan_id: int, done: int):
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("UPDATE plans SET done=? WHERE id=?", (done, plan_id))


def get_week_plan_stats(user_id: int) -> dict:
    today = date.today()
    week_ago = str(today - timedelta(days=6))
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""SELECT subject, COUNT(*) as planned, SUM(done) as done
                     FROM plans WHERE user_id=? AND date BETWEEN ? AND ?
                     GROUP BY subject""", (user_id, week_ago, str(today)))
        return {r["subject"]: {"planned": r["planned"], "done": r["done"] or 0}
                for r in c.fetchall()}


# ── EGE ───────────────────────────────────────────────────

def save_ege_settings(user_id: int, subjects: list, schedule: dict):
    if not user_id or not subjects:
        return
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM ege_settings WHERE user_id=?", (user_id,))
        if c.fetchone():
            c.execute("UPDATE ege_settings SET subjects=?, schedule=? WHERE user_id=?",
                      (json.dumps(subjects, ensure_ascii=False),
                       json.dumps(schedule, ensure_ascii=False), user_id))
        else:
            c.execute("INSERT INTO ege_settings (user_id, subjects, schedule) VALUES (?,?,?)",
                      (user_id, json.dumps(subjects, ensure_ascii=False),
                       json.dumps(schedule, ensure_ascii=False)))
        conn.commit()


def get_ege_settings(user_id: int) -> dict | None:
    if not user_id:
        return None
    try:
        with sqlite3.connect(DB) as conn:
            c = conn.cursor()
            c.execute("SELECT subjects, schedule FROM ege_settings WHERE user_id=?", (user_id,))
            row = c.fetchone()
            if not row:
                return None
            return {
                "subjects": json.loads(row[0]),
                "schedule": json.loads(row[1]),
            }
    except Exception:
        return None


def get_today_ege_subjects(user_id: int) -> list[str]:
    """Возвращает предметы, запланированные на сегодня по расписанию."""
    settings = get_ege_settings(user_id)
    if not settings:
        return []
    dow_map = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
    today_dow = dow_map[date.today().weekday()]
    return settings["schedule"].get(today_dow, [])


def save_ege_task(user_id: int, subject: str, task_type: str, task_number: int = None):
    if not user_id or not subject:
        return
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO ege_tasks (user_id, date, subject, task_type, task_number)
                     VALUES (?,?,?,?,?)""",
                  (user_id, today, subject, task_type, task_number))
        conn.commit()


def mark_ege_task_done(user_id: int, subject: str, task_number: int = None):
    if not user_id or not subject:
        return
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("""UPDATE ege_tasks SET done=1
                     WHERE user_id=? AND date=? AND subject=?
                     AND (task_number=? OR task_number IS NULL)""",
                  (user_id, today, subject, task_number))
        # Обновляем прогресс
        if task_number:
            c.execute("""INSERT INTO ege_progress (user_id, subject, task_number, times_done, last_done)
                         VALUES (?,?,?,1,?)
                         ON CONFLICT(user_id, subject, task_number)
                         DO UPDATE SET times_done=times_done+1, last_done=?""",
                      (user_id, subject, task_number, today, today))
        conn.commit()


def get_ege_progress(user_id: int, subject: str) -> dict:
    """Возвращает {task_number: times_done} для предмета."""
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""SELECT task_number, times_done, last_done FROM ege_progress
                     WHERE user_id=? AND subject=? ORDER BY task_number""",
                  (user_id, subject))
        return {r["task_number"]: {"times": r["times_done"], "last": r["last_done"]}
                for r in c.fetchall()}


def get_week_ege_stats(user_id: int) -> dict:
    today = date.today()
    week_ago = str(today - timedelta(days=6))
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""SELECT subject, task_type, task_number, done
                     FROM ege_tasks
                     WHERE user_id=? AND date BETWEEN ? AND ?""",
                  (user_id, week_ago, str(today)))
        rows = [dict(r) for r in c.fetchall()]
    return rows
