"""
bot.py — точка входа.

Запуск:  python bot.py

Что делает:
  • Регистрирует все команды
  • Планировщик (APScheduler):
      - 07:00 → напоминание утром
      - 22:00 → вечерний дневник
      - Воскресенье 20:00 → недельный отчёт
      - Рандомные напоминания в окне (по настройкам юзера)
"""

import logging
import os
import random
from datetime import datetime, time, timedelta

from dotenv import load_dotenv

from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)

from database import create_tables, get_or_create_user, get_all_user_tg_ids
from handlers import morning_conv, evening_conv, notify_conv, stats_command, send_weekly_report

# ── Логи ──────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# КОМАНДЫ
# ═══════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username or "")
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я твой личный дневник самочувствия.\n\n"
        "*Команды:*\n"
        "/morning — утренний опрос\n"
        "/evening — вечерний дневник\n"
        "/stats   — недельный отчёт\n"
        "/notify  — настроить уведомления\n"
        "/help    — справка",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*📖 Справка*\n\n"
        "*/morning* — утренний опрос (сон, телефон)\n"
        "*/evening* — вечерний (настроение, энергия, привычки)\n"
        "*/stats*   — недельный отчёт прямо сейчас\n"
        "*/notify*  — настроить время напоминаний\n\n"
        "Фиксированные напоминания:\n"
        "• 07:30 → утренний опрос\n"
        "• 22:00 → вечерний дневник\n"
        "• Воскресенье 20:00 → недельный отчёт",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════
# ПЛАНИРОВЩИК — джобы
# ═══════════════════════════════════════════════════════════

async def job_morning_reminder(context: ContextTypes.DEFAULT_TYPE):
    """07:30 — напоминание заполнить утренний опрос."""
    for tg_id in get_all_user_tg_ids():
        try:
            await context.bot.send_message(
                tg_id,
                "🌅 Доброе утро! Не забудь заполнить утренний дневник.\n/morning"
            )
        except Exception as e:
            log.warning(f"Не смог отправить morning reminder {tg_id}: {e}")


async def job_evening_reminder(context: ContextTypes.DEFAULT_TYPE):
    """22:00 — напоминание заполнить вечерний дневник."""
    for tg_id in get_all_user_tg_ids():
        try:
            await context.bot.send_message(
                tg_id,
                "🌙 Время вечернего дневника! Как прошёл день?\n/evening"
            )
        except Exception as e:
            log.warning(f"Не смог отправить evening reminder {tg_id}: {e}")


async def job_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Воскресенье 20:00 — недельный отчёт."""
    for tg_id in get_all_user_tg_ids():
        try:
            await send_weekly_report(tg_id, context)
        except Exception as e:
            log.warning(f"Не смог отправить weekly report {tg_id}: {e}")


async def job_random_reminder(context: ContextTypes.DEFAULT_TYPE):
    """
    Напоминание в дневное окно (по умолчанию 13:00–16:00).
    Шлём один раз — планировщик вызывает эту джобу несколько раз в день.
    """
    messages = [
        "👋 Как ты сейчас?",
        "💧 Выпил воды?",
        "🧘 Минутка осознанности — как дела?",
        "📋 Не забудь вечером заполнить дневник!",
    ]
    for tg_id in get_all_user_tg_ids():
        try:
            await context.bot.send_message(tg_id, random.choice(messages))
        except Exception as e:
            log.warning(f"Не смог отправить random reminder {tg_id}: {e}")


# ═══════════════════════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════════════════════

def main():
    load_dotenv()
    create_tables()

    token = os.getenv("TOKEN")
    if not token:
        raise ValueError("Переменная TOKEN не найдена в .env")

    app = Application.builder().token(token).build()

    # ── Регистрация хендлеров ──────────────────────────────
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("help",    help_command))
    app.add_handler(CommandHandler("stats",   stats_command))
    app.add_handler(morning_conv)
    app.add_handler(evening_conv)
    app.add_handler(notify_conv)

    # ── Планировщик ───────────────────────────────────────
    jq = app.job_queue

    # Утреннее напоминание — каждый день 07:30
    jq.run_daily(job_morning_reminder, time=time(7, 30))

    # Вечернее напоминание — каждый день 22:00
    jq.run_daily(job_evening_reminder, time=time(22, 0))

    # Недельный отчёт — каждое воскресенье 20:00
    jq.run_daily(
        job_weekly_report,
        time=time(20, 0),
        days=(6,)  # 6 = воскресенье (0=пн … 6=вс)
    )

    # Дневные напоминания — 3 раза между 13:00 и 16:00
    # Рандомизация: каждый день в разное время внутри окна
    for offset_min in [0, 60, 120]:   # примерно каждый час
        remind_time = time(13 + offset_min // 60, offset_min % 60)
        jq.run_daily(job_random_reminder, time=remind_time)

    log.info("Бот запущен ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
