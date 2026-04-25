import sqlite3
from datetime import date, timedelta

DB = "diary.db"


def create_tables():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Пользователи
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id       INTEGER UNIQUE NOT NULL,
            username    TEXT,
            streak      INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (date('now'))
        )
    """)

    # Записи дневника (утро + вечер объединены по дате)
    c.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            date            TEXT DEFAULT (date('now')),
            mode            TEXT,           -- 'morning' / 'evening'

            -- Утро
            sleep_h         REAL,           -- часы сна (7.5)
            sleep_q         INTEGER,        -- качество 1-5
            dreams          INTEGER,        -- 0/1
            phone_morning   INTEGER,        -- 0/1

            -- Вечер
            mood            INTEGER,        -- 1-5
            energy          INTEGER,        -- 1-5
            sport           INTEGER,        -- 0/1
            water           INTEGER,        -- стаканы
            food_ok         INTEGER,        -- 0/1 (нормально поел)
            meditation      INTEGER,        -- 0/1
            reading         INTEGER,        -- 0/1
            social          INTEGER,        -- 0/1 (общение вживую)
            note            TEXT,           -- свободная заметка

            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Настройки уведомлений
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER UNIQUE,     -- один набор настроек на юзера
            time_from   TEXT DEFAULT '13:00',
            time_to     TEXT DEFAULT '16:00',
            days        TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri',
            count       INTEGER DEFAULT 3,
            is_active   INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# ── Пользователи ─────────────────────────────────────────

def get_or_create_user(tg_id: int, username: str) -> int:
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
        row = c.fetchone()
        if row:
            return row[0]
        c.execute("INSERT INTO users (tg_id, username) VALUES (?, ?)", (tg_id, username))
        return c.lastrowid


def get_user_id(tg_id: int) -> int | None:
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
        row = c.fetchone()
        return row[0] if row else None


def get_all_user_tg_ids() -> list[int]:
    """Все tg_id — нужно для рассылки уведомлений."""
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT tg_id FROM users")
        return [row[0] for row in c.fetchall()]


# ── Записи ───────────────────────────────────────────────

def save_entry(user_id: int, mode: str, data: dict):
    """
    Сохраняет запись. Если запись за сегодня уже есть — обновляет нужные поля.
    Так утро и вечер за один день не дублируются.
    """
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id FROM entries WHERE user_id = ? AND date = ? AND mode = ?",
            (user_id, today, mode)
        )
        row = c.fetchone()

        if mode == "morning":
            fields = ("sleep_h", "sleep_q", "dreams", "phone_morning")
        else:
            fields = ("mood", "energy", "sport", "water", "food_ok",
                      "meditation", "reading", "social", "note")

        if row:
            # Обновляем существующую запись
            sets = ", ".join(f"{f} = ?" for f in fields)
            vals = [data.get(f) for f in fields] + [row[0]]
            c.execute(f"UPDATE entries SET {sets} WHERE id = ?", vals)
        else:
            # Новая запись
            cols = "user_id, date, mode, " + ", ".join(fields)
            placeholders = ", ".join(["?"] * (3 + len(fields)))
            vals = [user_id, today, mode] + [data.get(f) for f in fields]
            c.execute(f"INSERT INTO entries ({cols}) VALUES ({placeholders})", vals)


# ── Недельная статистика ──────────────────────────────────

def get_week_stats(user_id: int) -> dict:
    """
    Возвращает агрегированную статистику за последние 7 дней.
    Используется для недельного отчёта.
    """
    today = date.today()
    week_ago = str(today - timedelta(days=6))
    today_str = str(today)

    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Все записи за неделю
        c.execute("""
            SELECT * FROM entries
            WHERE user_id = ? AND date BETWEEN ? AND ?
            ORDER BY date ASC
        """, (user_id, week_ago, today_str))
        rows = c.fetchall()

    if not rows:
        return {}

    # Собираем данные по дням (объединяем утро и вечер одного дня)
    days: dict[str, dict] = {}
    for r in rows:
        d = r["date"]
        if d not in days:
            days[d] = {}
        days[d].update({k: r[k] for k in r.keys() if r[k] is not None})

    # Считаем средние и проценты
    def avg(key):
        vals = [v[key] for v in days.values() if v.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def pct(key):
        vals = [v[key] for v in days.values() if v.get(key) is not None]
        return round(sum(vals) / len(vals) * 100) if vals else None

    # Настроение по дням недели
    dow_map = {"Mon": "Пн", "Tue": "Вт", "Wed": "Ср",
               "Thu": "Чт", "Fri": "Пт", "Sat": "Сб", "Sun": "Вс"}
    mood_by_dow = {}
    for d, v in days.items():
        if v.get("mood"):
            dow = date.fromisoformat(d).strftime("%a")
            ru = dow_map.get(dow, dow)
            mood_by_dow[ru] = v["mood"]

    # Инсайты — простая аналитика
    insights = []

    sleep_vals = [v.get("sleep_h") for v in days.values() if v.get("sleep_h")]
    mood_vals = [v.get("mood") for v in days.values() if v.get("mood")]

    if sleep_vals and mood_vals:
        good_sleep_moods = [
            days[d].get("mood") for d in days
            if days[d].get("sleep_h", 0) >= 7 and days[d].get("mood")
        ]
        bad_sleep_moods = [
            days[d].get("mood") for d in days
            if days[d].get("sleep_h") and days[d]["sleep_h"] < 7 and days[d].get("mood")
        ]
        if good_sleep_moods and bad_sleep_moods:
            diff = round(
                sum(good_sleep_moods)/len(good_sleep_moods) -
                sum(bad_sleep_moods)/len(bad_sleep_moods), 1
            )
            if diff > 0.3:
                insights.append(
                    f"😴 Когда спишь 7+ часов, настроение в среднем на {diff} балла выше"
                )

    sport_days = [d for d in days if days[d].get("sport") == 1]
    no_sport_days = [d for d in days if days[d].get("sport") == 0 and days[d].get("mood")]
    if sport_days and no_sport_days:
        sm = [days[d]["mood"] for d in sport_days if days[d].get("mood")]
        nm = [days[d]["mood"] for d in no_sport_days]
        if sm and nm:
            insights.append(
                f"🏃 В дни со спортом настроение {round(sum(sm)/len(sm),1)} "
                f"против {round(sum(nm)/len(nm),1)} без него"
            )

    phone_bad = [d for d in days if days[d].get("phone_morning") == 1 and days[d].get("mood")]
    phone_total = [d for d in days if days[d].get("phone_morning") is not None]
    if phone_bad and phone_total:
        pct_phone = round(len(phone_bad) / len(phone_total) * 100)
        insights.append(
            f"📱 Утренний телефон — в {pct_phone}% дней этой недели"
        )

    return {
        "days_count": len(days),
        "avg_mood": avg("mood"),
        "avg_sleep_h": avg("sleep_h"),
        "avg_sleep_q": avg("sleep_q"),
        "avg_energy": avg("energy"),
        "streak": len(days),
        "sport_pct": pct("sport"),
        "meditation_pct": pct("meditation"),
        "reading_pct": pct("reading"),
        "water_avg": avg("water"),
        "social_pct": pct("social"),
        "phone_morning_pct": pct("phone_morning"),
        "mood_by_dow": mood_by_dow,
        "insights": insights,
    }


# ── Уведомления ──────────────────────────────────────────

def get_notification_settings(user_id: int) -> dict | None:
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM notifications WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return dict(row) if row else None


def save_notification_settings(user_id: int, settings: dict):
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM notifications WHERE user_id = ?", (user_id,))
        exists = c.fetchone()
        if exists:
            c.execute("""
                UPDATE notifications
                SET time_from=?, time_to=?, days=?, count=?, is_active=?
                WHERE user_id=?
            """, (
                settings.get("time_from", "13:00"),
                settings.get("time_to", "16:00"),
                settings.get("days", "Mon,Tue,Wed,Thu,Fri"),
                settings.get("count", 3),
                settings.get("is_active", 1),
                user_id
            ))
        else:
            c.execute("""
                INSERT INTO notifications (user_id, time_from, time_to, days, count, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                settings.get("time_from", "13:00"),
                settings.get("time_to", "16:00"),
                settings.get("days", "Mon,Tue,Wed,Thu,Fri"),
                settings.get("count", 3),
                settings.get("is_active", 1),
            ))
