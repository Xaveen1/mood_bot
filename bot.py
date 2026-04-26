"""
bot.py — точка входа.

Меню:
  🌅 Утренний опрос    → morning_conv
  🌙 Вечерний дневник  → evening_conv
  📋 План на день      → plan_conv
  ✅ Отметить выполнено → done_start
  📊 Мой день          → today_view
  📈 Отчёт за неделю   → report_command

Автоматика (по МСК):
  07:30  → напоминание утро
  22:00  → напоминание вечер
  Вс 20:00 → недельный отчёт
  13:00 / 14:30 / 16:00 → дневные напоминания
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

from database import init_db, upsert_user, all_tg_ids
from keyboards import main_kb
from morning import morning_conv
from evening import evening_conv
from planner import (
    plan_conv, done_start, toggle_done, today_view
)
from report import report_command, send_weekly_to_all

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# БАЗОВЫЕ КОМАНДЫ
# ═══════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username or "", user.first_name or "")
    await update.message.reply_text(
        f"Привет, *{user.first_name}*! 👋\n\n"
        "Я твой личный дневник — слежу за самочувствием, "
        "сном, привычками и задачами.\n\n"
        "Каждое утро буду писать тебе сам 🌅\n"
        "Каждое воскресенье — недельный отчёт 📊\n\n"
        "Используй кнопки внизу 👇",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*📖 Как пользоваться*\n\n"
        "🌅 *Утренний опрос* — сон, качество, телефон\n"
        "🌙 *Вечерний дневник* — настроение, энергия, привычки\n"
        "📋 *План на день* — выбрать задачи на сегодня\n"
        "✅ *Отметить выполнено* — отметить что сделал\n"
        "📊 *Мой день* — посмотреть план\n"
        "📈 *Отчёт за неделю* — аналитика + инсайты\n\n"
        "*Автоматически:*\n"
        "• 07:30 → напоминание заполнить утро\n"
        "• 13:00, 14:30, 16:00 → дневные напоминания\n"
        "• 22:00 → напоминание вечернего дневника\n"
        "• Каждое воскресенье 20:00 → недельный отчёт",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )


# ═══════════════════════════════════════════════════════════
# ПЛАНИРОВЩИК — джобы
# ═══════════════════════════════════════════════════════════

async def job_morning(ctx: ContextTypes.DEFAULT_TYPE):
    for tg_id in all_tg_ids():
        try:
            await ctx.bot.send_message(
                tg_id,
                "🌅 *Доброе утро!*\n\n"
                "Заполни утренний опрос — займёт 30 секунд 👇",
                parse_mode="Markdown",
                reply_markup=main_kb()
            )
        except Exception as e:
            log.warning(f"morning job {tg_id}: {e}")


async def job_evening(ctx: ContextTypes.DEFAULT_TYPE):
    for tg_id in all_tg_ids():
        try:
            await ctx.bot.send_message(
                tg_id,
                "🌙 *Время подвести итог дня!*\n\n"
                "Заполни вечерний дневник — займёт минуту 👇",
                parse_mode="Markdown",
                reply_markup=main_kb()
            )
        except Exception as e:
            log.warning(f"evening job {tg_id}: {e}")


async def job_random(ctx: ContextTypes.DEFAULT_TYPE):
    msgs = [
        "💧 Пил воду сегодня? Выпей стакан прямо сейчас!",
        "📋 Как план на день — всё идёт по графику?",
        "🧘 Минута осознанности: как ты сейчас себя чувствуешь?",
        "🏃 Не забудь про активность сегодня — даже прогулка считается!",
        "⚡ Уровень энергии как? Может, пора сделать перерыв?",
    ]
    for tg_id in all_tg_ids():
        try:
            await ctx.bot.send_message(tg_id, random.choice(msgs))
        except Exception as e:
            log.warning(f"random job {tg_id}: {e}")


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
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("stats", report_command))

    # ── ConversationHandler-ы (порядок важен!) ────────────
    app.add_handler(morning_conv)
    app.add_handler(evening_conv)
    app.add_handler(plan_conv)

    # ── Кнопки главного меню ──────────────────────────────
    app.add_handler(MessageHandler(
        filters.Regex("^✅ Отметить выполнено$"), done_start))
    app.add_handler(MessageHandler(
        filters.Regex("^📊 Мой день$"), today_view))
    app.add_handler(MessageHandler(
        filters.Regex("^📈 Отчёт за неделю$"), report_command))

    # ── Inline кнопки (отметка выполненного) ─────────────
    app.add_handler(CallbackQueryHandler(toggle_done, pattern="^td:"))

    # ── Планировщик ───────────────────────────────────────
    jq = app.job_queue

    jq.run_daily(job_morning,  time=time(7, 30))   # 07:30 каждый день
    jq.run_daily(job_evening,  time=time(22, 0))   # 22:00 каждый день
    jq.run_daily(job_random,   time=time(13, 0))   # 13:00
    jq.run_daily(job_random,   time=time(14, 30))  # 14:30
    jq.run_daily(job_random,   time=time(16, 0))   # 16:00
    jq.run_daily(                                  # вс 20:00 — недельный отчёт
        send_weekly_to_all,
        time=time(20, 0),
        days=(6,)
    )

    log.info("✅ Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
