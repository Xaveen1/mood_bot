"""
plan_database.py — всё что связано с задачами/планом дня.
"""

import sqlite3
from datetime import date, timedelta
from database import DB


def create_plan_tables():
    """Вызывается один раз при старте бота."""
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                date        TEXT DEFAULT (date('now')),
                subject     TEXT NOT NULL,   -- 'ege', 'python', 'sport', 'reading'
                task_type   TEXT,            -- 'Новые задания', 'Теория' и т.д.
                done        INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()


def save_plan(user_id: int, subject: str, task_type: str):
    """Сохраняет одну задачу на сегодня. Дубли по subject заменяет."""
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id FROM plans WHERE user_id=? AND date=? AND subject=?",
            (user_id, today, subject)
        )
        row = c.fetchone()
        if row:
            c.execute(
                "UPDATE plans SET task_type=?, done=0 WHERE id=?",
                (task_type, row[0])
            )
        else:
            c.execute(
                "INSERT INTO plans (user_id, date, subject, task_type) VALUES (?,?,?,?)",
                (user_id, today, subject, task_type)
            )


def get_today_plan(user_id: int) -> list[dict]:
    """Возвращает список задач на сегодня."""
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT * FROM plans WHERE user_id=? AND date=? ORDER BY id",
            (user_id, today)
        )
        return [dict(r) for r in c.fetchall()]


def mark_done(user_id: int, subject: str, done: int):
    """Отмечает задачу выполненной (done=1) или нет (done=0)."""
    today = str(date.today())
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE plans SET done=? WHERE user_id=? AND date=? AND subject=?",
            (done, user_id, today, subject)
        )


def get_week_task_stats(user_id: int) -> dict:
    """
    Статистика за 7 дней для недельного отчёта.
    Возвращает: { 'ege': {'planned': 5, 'done': 4}, ... }
    """
    today = date.today()
    week_ago = str(today - timedelta(days=6))
    today_str = str(today)

    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT subject, COUNT(*) as planned, SUM(done) as done
            FROM plans
            WHERE user_id=? AND date BETWEEN ? AND ?
            GROUP BY subject
        """, (user_id, week_ago, today_str))
        rows = c.fetchall()

    return {
        r["subject"]: {
            "planned": r["planned"],
            "done": r["done"] or 0
        }
        for r in rows
    }
