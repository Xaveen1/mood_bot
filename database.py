import sqlite3
from datetime import date, timedelta

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
                created_at TEXT DEFAULT (date('now'))
            );

            CREATE TABLE IF NOT EXISTS entries (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                date          TEXT NOT NULL,
                -- утро
                sleep_h       REAL,
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
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                date      TEXT NOT NULL,
                subject   TEXT NOT NULL,
                task_type TEXT,
                done      INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


# ── users ────────────────────────────────────────────────

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


def all_tg_ids() -> list[int]:
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT tg_id FROM users")
        return [r[0] for r in c.fetchall()]


# ── entries ───────────────────────────────────────────────

def save_morning(user_id: int, data: dict):
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM entries WHERE user_id=? AND date=?", (user_id, today))
        row = c.fetchone()
        if row:
            c.execute("""UPDATE entries SET sleep_h=?, sleep_q=?, dreams=?, phone_morning=?
                         WHERE id=?""",
                      (data.get("sleep_h"), data.get("sleep_q"),
                       data.get("dreams"), data.get("phone_morning"), row[0]))
        else:
            c.execute("""INSERT INTO entries (user_id, date, sleep_h, sleep_q, dreams, phone_morning)
                         VALUES (?,?,?,?,?,?)""",
                      (user_id, today, data.get("sleep_h"), data.get("sleep_q"),
                       data.get("dreams"), data.get("phone_morning")))


def save_evening(user_id: int, data: dict):
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

    dow_names = {"Mon":"Пн","Tue":"Вт","Wed":"Ср","Thu":"Чт","Fri":"Пт","Sat":"Сб","Sun":"Вс"}
    mood_by_dow = {}
    for r in rows:
        if r.get("mood"):
            dow = date.fromisoformat(r["date"]).strftime("%a")
            mood_by_dow[dow_names.get(dow, dow)] = r["mood"]

    # инсайты
    insights = []
    good = [r["mood"] for r in rows if r.get("sleep_h", 0) >= 7 and r.get("mood")]
    bad  = [r["mood"] for r in rows if r.get("sleep_h") and r["sleep_h"] < 7 and r.get("mood")]
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
        insights.append(f"📱 Телефон утром — в {round(len(ph_bad)/len(ph)*100)}% дней")

    return {
        "days": len(rows),
        "avg_mood": avg("mood"),
        "avg_sleep_h": avg("sleep_h"),
        "avg_sleep_q": avg("sleep_q"),
        "avg_energy": avg("energy"),
        "sport_pct": pct("sport"),
        "meditation_pct": pct("meditation"),
        "reading_pct": pct("reading"),
        "social_pct": pct("social"),
        "water_avg": avg("water"),
        "mood_by_dow": mood_by_dow,
        "insights": insights,
    }


# ── plans ─────────────────────────────────────────────────

def save_plan(user_id: int, subject: str, task_type: str):
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM plans WHERE user_id=? AND date=? AND subject=?",
                  (user_id, today, subject))
        row = c.fetchone()
        if row:
            c.execute("UPDATE plans SET task_type=?, done=0 WHERE id=?", (task_type, row[0]))
        else:
            c.execute("INSERT INTO plans (user_id, date, subject, task_type) VALUES (?,?,?,?)",
                      (user_id, today, subject, task_type))


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
