"""
bot.py — точка входа.

Время: UTC+5 (Пермь). Все джобы планировщика в UTC+5.

Меню:
  🌅 Утренний опрос     morning_conv
  🌙 Вечерний дневник   evening_conv
  📚 ЕГЭ                ege_today + ege_session_conv
  📋 План на день        plan_conv
  ✅ Отметить            done_start
  📊 Мой день            today_view
  📈 Отчёт недели        report_command
  🤖 AI-тренер           ai_coach_handler

Автоматика (время Пермь UTC+5 → в UTC отнимаем 5):
  07:30 (Пермь) = 02:30 UTC → напоминание утро
  22:00 (Пермь) = 17:00 UTC → напоминание вечер
  Вс 20:00 (Пермь) = 15:00 UTC → недельный отчёт
  13:00, 14:30, 16:00 Пермь = 08:00, 09:30, 11:00 UTC
"""

import logging
import os
import random
from datetime import time

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from database import init_db, upsert_user, all_users
from keyboards import main_kb
from morning import morning_conv
from evening import evening_conv
from ege import ege_today, setup_conv, ege_session_conv, ege_progress_view
from planner import plan_conv, done_start, toggle_done, today_view
from report import report_command, send_weekly_to_all
from ai_coach import ai_coach_handler

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# КОМАНДЫ
# ═══════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username or "", user.first_name or "")
    await update.message.reply_text(
        f"Привет, *{user.first_name}*! 👋\n\n"
        "Я твой личный дневник и ЕГЭ-тренер.\n\n"
        "🌅 Каждое утро буду писать тебе\n"
        "📊 По воскресеньям — полный отчёт\n"
        "🤖 AI-тренер анализирует твою неделю\n\n"
        "Для начала настрой ЕГЭ: /ege\\_setup\n\n"
        "Используй кнопки внизу 👇",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*📖 Справка*\n\n"
        "🌅 *Утренний опрос* — сон (с точностью до 15 мин), телефон\n"
        "🌙 *Вечерний дневник* — настроение, энергия, привычки\n"
        "📚 *ЕГЭ* — занятие по расписанию, трекинг заданий\n"
        "📋 *План на день* — задачи + свои + напоминания\n"
        "✅ *Отметить* — отметить выполненное\n"
        "📊 *Мой день* — план на сегодня\n"
        "📈 *Отчёт недели* — полная аналитика\n"
        "🤖 *AI-тренер* — персональные советы от Claude\n\n"
        "*/ege\\_setup* — настроить предметы и расписание ЕГЭ\n"
        "*/ege\\_progress* — прогресс по заданиям\n\n"
        "*Автоматически (время Пермь):*\n"
        "• 07:30 → утреннее напоминание\n"
        "• 13:00, 14:30, 16:00 → дневные напоминания\n"
        "• 22:00 → вечерний дневник\n"
        "• Вс 20:00 → недельный отчёт",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )


# ═══════════════════════════════════════════════════════════
# ПЛАНИРОВЩИК
# ═══════════════════════════════════════════════════════════

# UTC+5 (Пермь) → UTC: отнимаем 5 часов
# 07:30 Пермь = 02:30 UTC
# 13:00 Пермь = 08:00 UTC
# 14:30 Пермь = 09:30 UTC
# 16:00 Пермь = 11:00 UTC
# 22:00 Пермь = 17:00 UTC
# Вс 20:00 Пермь = Вс 15:00 UTC

async def job_morning(ctx: ContextTypes.DEFAULT_TYPE):
    msgs = [
        "🌅 *Доброе утро!*\n\nЗаполни утренний опрос — 30 секунд 👇",
        "🌅 Новый день — новые возможности!\n\nБыстрый утренний опрос? 👇",
        "☀️ *Подъём!*\n\nКак спалось? Заполни дневник 👇",
    ]
    for u in all_users():
        try:
            await ctx.bot.send_message(
                u["tg_id"],
                random.choice(msgs),
                parse_mode="Markdown",
                reply_markup=main_kb()
            )
        except Exception as e:
            log.warning(f"morning {u['tg_id']}: {e}")


async def job_evening(ctx: ContextTypes.DEFAULT_TYPE):
    msgs = [
        "🌙 *Время подвести итог дня!*\n\nВечерний дневник → «🌙 Вечерний дневник»",
        "🌙 Как прошёл день?\n\nЗаполни вечерний дневник — займёт минуту 👇",
    ]
    for u in all_users():
        try:
            await ctx.bot.send_message(
                u["tg_id"],
                random.choice(msgs),
                parse_mode="Markdown",
                reply_markup=main_kb()
            )
        except Exception as e:
            log.warning(f"evening {u['tg_id']}: {e}")


async def job_day_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    msgs = [
        "💧 Пил воду сегодня? Выпей стакан прямо сейчас!",
        "📋 Как план на день — всё по графику?",
        "🧘 Секунда осознанности: как ты сейчас?",
        "⚡ Уровень энергии? Может, пора сделать перерыв на 5 минут?",
        "📚 Не забудь про ЕГЭ сегодня — даже 30 минут делают разницу!",
        "🏃 Спорт сегодня? Даже короткая прогулка считается!",
        "📵 Ты не смотришь в телефон слишком часто? 😉",
    ]
    for u in all_users():
        try:
            await ctx.bot.send_message(u["tg_id"], random.choice(msgs))
        except Exception as e:
            log.warning(f"day reminder {u['tg_id']}: {e}")


async def job_custom_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    """Проверяет кастомные напоминания из планов и отправляет их."""
    import sqlite3
    from datetime import datetime, date
    from database import DB

    now_perm = datetime.utcnow()
    # UTC+5
    hour = (now_perm.hour + 5) % 24
    current_time = f"{hour:02d}:{now_perm.minute:02d}"
    today = str(date.today())

    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT p.id, p.task_type, p.remind_at, u.tg_id
            FROM plans p
            JOIN users u ON u.id = p.user_id
            WHERE p.date=? AND p.remind_at IS NOT NULL AND p.done=0
        """, (today,))
        rows = c.fetchall()

    for r in rows:
        remind_h, remind_m = r["remind_at"].split(":")
        now_h, now_m = current_time.split(":")
        if remind_h == now_h and abs(int(now_m) - int(remind_m)) <= 2:
            try:
                await ctx.bot.send_message(
                    r["tg_id"],
                    f"⏰ *Напоминание!*\n\n📝 {r['task_type']}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                log.warning(f"custom reminder: {e}")


# ═══════════════════════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════════════════════

def main():
    load_dotenv()
    init_db()

    token = os.getenv("TOKEN")
    if not token:
        raise ValueError("TOKEN не найден — добавь в Railway Variables: TOKEN=...")

    app = Application.builder().token(token).build()

    # ── Базовые команды ───────────────────────────────────
    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("help",         cmd_help))
    app.add_handler(CommandHandler("stats",        report_command))
    app.add_handler(CommandHandler("ege_progress", ege_progress_view))

    # ── ConversationHandler-ы (порядок важен!) ────────────
    app.add_handler(morning_conv)
    app.add_handler(evening_conv)
    app.add_handler(setup_conv)
    app.add_handler(ege_session_conv)
    app.add_handler(plan_conv)

    # ── Кнопки меню ───────────────────────────────────────
    app.add_handler(MessageHandler(filters.Regex("^📚 ЕГЭ$"),            ege_today))
    app.add_handler(MessageHandler(filters.Regex("^✅ Отметить$"),        done_start))
    app.add_handler(MessageHandler(filters.Regex("^📊 Мой день$"),        today_view))
    app.add_handler(MessageHandler(filters.Regex("^📈 Отчёт недели$"),    report_command))
    app.add_handler(MessageHandler(filters.Regex("^🤖 AI-тренер$"),       ai_coach_handler))

    # ── Inline кнопки ────────────────────────────────────
    app.add_handler(CallbackQueryHandler(toggle_done, pattern="^td:"))

    # ── Планировщик ──────────────────────────────────────
    jq = app.job_queue

    # Время в UTC (Пермь = UTC+5, отнимаем 5)
    jq.run_daily(job_morning,     time=time(2, 30))   # 07:30 Пермь
    jq.run_daily(job_day_reminder,time=time(8, 0))    # 13:00 Пермь
    jq.run_daily(job_day_reminder,time=time(9, 30))   # 14:30 Пермь
    jq.run_daily(job_day_reminder,time=time(11, 0))   # 16:00 Пермь
    jq.run_daily(job_evening,     time=time(17, 0))   # 22:00 Пермь

    # Вс 20:00 Пермь = Вс 15:00 UTC
    jq.run_daily(send_weekly_to_all, time=time(15, 0), days=(6,))

    # Кастомные напоминания — проверяем каждые 5 минут
    jq.run_repeating(job_custom_reminders, interval=300, first=10)

    log.info("✅ Бот запущен — время Пермь UTC+5")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
