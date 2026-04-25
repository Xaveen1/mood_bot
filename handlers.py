"""
handlers.py — все обработчики бота.

Структура:
  morning_conv  — утренний опрос (3 шага)
  evening_conv  — вечерний опрос (7 шагов)
  notify_conv   — настройка уведомлений
  stats_handler — /stats → недельный отчёт вручную
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from database import get_user_id, save_entry, get_week_stats

# ── Шаги диалогов ────────────────────────────────────────

# Утро
SLEEP_H, SLEEP_Q, DREAMS, PHONE = range(4)

# Вечер
E_MOOD, E_ENERGY, E_SPORT, E_WATER, E_HABITS, E_SOCIAL, E_NOTE = range(10, 17)

# Уведомления
N_FROM, N_TO, N_DAYS, N_COUNT = range(20, 24)


# ── Вспомогалки ──────────────────────────────────────────

def kb(buttons: list[list]) -> InlineKeyboardMarkup:
    """Строит inline-клавиатуру из списка списков."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(b), callback_data=str(b)) for b in row]
        for row in buttons
    ])


# ═══════════════════════════════════════════════════════════
# УТРЕННИЙ ОПРОС
# ═══════════════════════════════════════════════════════════

async def morning_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌅 *Доброе утро!* Быстрый опрос — 4 вопроса.\n\n"
        "Сколько часов спал?",
        parse_mode="Markdown",
        reply_markup=kb([["5", "6", "7", "8", "9+"]])
    )
    return SLEEP_H


async def got_sleep_h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    val = query.data
    # "9+" сохраняем как 9
    context.user_data["sleep_h"] = float(val.replace("+", ""))
    await query.edit_message_text(
        "Как оцениваешь качество сна?",
        reply_markup=kb([[1, 2, 3, 4, 5]])
    )
    return SLEEP_Q


async def got_sleep_q(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["sleep_q"] = int(query.data)
    await query.edit_message_text(
        "Были сны?",
        reply_markup=kb([["Да 💭", "Нет"]])
    )
    return DREAMS


async def got_dreams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["dreams"] = 1 if "Да" in query.data else 0
    await query.edit_message_text(
        "Смотрел в телефон первые 20 минут после пробуждения?",
        reply_markup=kb([["Да 📱", "Нет 🙅"]])
    )
    return PHONE


async def got_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["phone_morning"] = 1 if "Да" in query.data else 0

    tg_id = update.effective_user.id
    user_id = get_user_id(tg_id)
    save_entry(user_id, mode="morning", data=context.user_data)

    await query.edit_message_text("✅ *Записал!* Хорошего дня 💪", parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END


morning_conv = ConversationHandler(
    entry_points=[CommandHandler("morning", morning_start)],
    states={
        SLEEP_H: [CallbackQueryHandler(got_sleep_h)],
        SLEEP_Q: [CallbackQueryHandler(got_sleep_q)],
        DREAMS:  [CallbackQueryHandler(got_dreams)],
        PHONE:   [CallbackQueryHandler(got_phone)],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: (
        u.message.reply_text("Отменил."), ConversationHandler.END
    )[-1])]
)


# ═══════════════════════════════════════════════════════════
# ВЕЧЕРНИЙ ОПРОС
# ═══════════════════════════════════════════════════════════

async def evening_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌙 *Вечерний дневник!*\n\nКак настроение сегодня?",
        parse_mode="Markdown",
        reply_markup=kb([[1, 2, 3, 4, 5]])
    )
    return E_MOOD


async def got_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["mood"] = int(query.data)
    await query.edit_message_text(
        "Как уровень энергии весь день?",
        reply_markup=kb([[1, 2, 3, 4, 5]])
    )
    return E_ENERGY


async def got_energy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["energy"] = int(query.data)
    await query.edit_message_text(
        "Был спорт / прогулка сегодня?",
        reply_markup=kb([["Да 🏃", "Нет"]])
    )
    return E_SPORT


async def got_sport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["sport"] = 1 if "Да" in query.data else 0
    await query.edit_message_text(
        "Сколько стаканов воды выпил?",
        reply_markup=kb([["0–2", "3–4", "5–6", "7–8", "8+"]])
    )
    return E_WATER


async def got_water(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Берём среднее из диапазона
    water_map = {"0–2": 1, "3–4": 3, "5–6": 5, "7–8": 7, "8+": 9}
    context.user_data["water"] = water_map.get(query.data, 4)
    await query.edit_message_text(
        "Что выполнил сегодня?\n_(можно выбрать несколько → потом нажми ✅ Готово)_",
        parse_mode="Markdown",
        reply_markup=_habits_kb(set())
    )
    return E_HABITS


def _habits_kb(selected: set) -> InlineKeyboardMarkup:
    """Клавиатура привычек с мультивыбором."""
    habits = [
        ("meditation", "🧘 Медитация"),
        ("reading",    "📚 Чтение"),
        ("food_ok",    "🥗 Нормально поел"),
    ]
    rows = []
    for key, label in habits:
        check = "✅ " if key in selected else ""
        rows.append([InlineKeyboardButton(check + label, callback_data=f"habit_{key}")])
    rows.append([InlineKeyboardButton("✅ Готово", callback_data="habit_done")])
    return InlineKeyboardMarkup(rows)


async def got_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if "habits_selected" not in context.user_data:
        context.user_data["habits_selected"] = set()

    selected = context.user_data["habits_selected"]

    if query.data == "habit_done":
        # Сохраняем выбранные привычки
        for key in ("meditation", "reading", "food_ok"):
            context.user_data[key] = 1 if key in selected else 0

        await query.edit_message_text(
            "Было живое общение с людьми сегодня?",
            reply_markup=kb([["Да 👥", "Нет"]])
        )
        return E_SOCIAL
    else:
        # Переключаем выбор привычки
        key = query.data.replace("habit_", "")
        if key in selected:
            selected.discard(key)
        else:
            selected.add(key)
        await query.edit_message_text(
            "Что выполнил сегодня?\n_(можно выбрать несколько → потом нажми ✅ Готово)_",
            parse_mode="Markdown",
            reply_markup=_habits_kb(selected)
        )
        return E_HABITS


async def got_social(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["social"] = 1 if "Да" in query.data else 0
    await query.edit_message_text(
        "Свободная заметка о дне ✏️\n_(напиши что угодно, или отправь /skip чтобы пропустить)_",
        parse_mode="Markdown"
    )
    return E_NOTE


async def got_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["note"] = update.message.text
    await _save_evening(update, context)
    return ConversationHandler.END


async def skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["note"] = None
    await _save_evening(update, context)
    return ConversationHandler.END


async def _save_evening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Финальное сохранение вечерней записи."""
    tg_id = update.effective_user.id
    user_id = get_user_id(tg_id)
    # Убираем вспомогательный ключ перед сохранением
    context.user_data.pop("habits_selected", None)
    save_entry(user_id, mode="evening", data=context.user_data)
    await update.message.reply_text(
        "🌙 *День записан!* Молодец, так держать 🔥\n\n"
        "В воскресенье получишь недельный отчёт.",
        parse_mode="Markdown"
    )
    context.user_data.clear()


evening_conv = ConversationHandler(
    entry_points=[CommandHandler("evening", evening_start)],
    states={
        E_MOOD:    [CallbackQueryHandler(got_mood)],
        E_ENERGY:  [CallbackQueryHandler(got_energy)],
        E_SPORT:   [CallbackQueryHandler(got_sport)],
        E_WATER:   [CallbackQueryHandler(got_water)],
        E_HABITS:  [CallbackQueryHandler(got_habits)],
        E_SOCIAL:  [CallbackQueryHandler(got_social)],
        E_NOTE:    [
            MessageHandler(filters.TEXT & ~filters.COMMAND, got_note),
            CommandHandler("skip", skip_note),
        ],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: (
        u.message.reply_text("Отменил."), ConversationHandler.END
    )[-1])]
)


# ═══════════════════════════════════════════════════════════
# НЕДЕЛЬНЫЙ ОТЧЁТ
# ═══════════════════════════════════════════════════════════

def _bar(value: float, max_val: float = 5, width: int = 10) -> str:
    """Текстовый прогресс-бар для отчёта."""
    filled = round(value / max_val * width)
    return "█" * filled + "░" * (width - filled)


async def send_weekly_report(user_tg_id: int, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет недельный отчёт пользователю.
    Вызывается из планировщика каждое воскресенье.
    """
    user_id = get_user_id(user_tg_id)
    if not user_id:
        return

    s = get_week_stats(user_id)
    if not s:
        await context.bot.send_message(
            user_tg_id,
            "📊 Недельный отчёт\n\nНедостаточно данных за неделю. "
            "Заполняй дневник каждый день — и на следующей неделе будет полный отчёт!"
        )
        return

    # ── Шапка ─────────────────────────────────────────────
    lines = [
        "╔════════════════════════════╗",
        "║  📊  НЕДЕЛЬНЫЙ ОТЧЁТ       ║",
        "╚════════════════════════════╝",
        f"Дней заполнено: *{s['days_count']} из 7*\n",
    ]

    # ── Ключевые метрики ──────────────────────────────────
    lines.append("*📈 Ключевые показатели*")
    if s.get("avg_mood"):
        lines.append(f"Настроение:  {_bar(s['avg_mood'])}  *{s['avg_mood']}/5*")
    if s.get("avg_energy"):
        lines.append(f"Энергия:     {_bar(s['avg_energy'])}  *{s['avg_energy']}/5*")
    if s.get("avg_sleep_h"):
        lines.append(f"Сон:         *{s['avg_sleep_h']}ч*  (качество {s.get('avg_sleep_q', '—')}/5)")
    lines.append(f"Стрик:       *{s['streak']} дн подряд* 🔥\n")

    # ── Настроение по дням недели ─────────────────────────
    if s.get("mood_by_dow"):
        lines.append("*📅 Настроение по дням*")
        for dow in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
            val = s["mood_by_dow"].get(dow)
            if val:
                lines.append(f"{dow}  {_bar(val)}  {val}")
        lines.append("")

    # ── Привычки ──────────────────────────────────────────
    lines.append("*✅ Привычки за неделю*")
    habits = [
        ("sport_pct",      "🏃 Спорт"),
        ("meditation_pct", "🧘 Медитация"),
        ("reading_pct",    "📚 Чтение"),
        ("social_pct",     "👥 Общение"),
    ]
    for key, label in habits:
        val = s.get(key)
        if val is not None:
            bar = _bar(val, max_val=100, width=10)
            lines.append(f"{label}  {bar}  *{val}%*")
    lines.append("")

    # ── Инсайты ───────────────────────────────────────────
    if s.get("insights"):
        lines.append("*💡 Инсайты недели*")
        for insight in s["insights"]:
            lines.append(f"▸ {insight}")
        lines.append("")

    lines.append("_Продолжай в том же духе! До следующего воскресенья 💪_")

    await context.bot.send_message(
        user_tg_id,
        "\n".join(lines),
        parse_mode="Markdown"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручной вызов отчёта через /stats."""
    await send_weekly_report(update.effective_user.id, context)


# ═══════════════════════════════════════════════════════════
# НАСТРОЙКИ УВЕДОМЛЕНИЙ
# ═══════════════════════════════════════════════════════════

async def notify_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔔 *Настройка уведомлений*\n\n"
        "Бот будет напоминать тебе заполнять дневник.\n\n"
        "С какого времени можно слать напоминания? (начало окна)",
        parse_mode="Markdown",
        reply_markup=kb([["10:00", "11:00", "12:00"], ["13:00", "14:00", "15:00"]])
    )
    return N_FROM


async def got_notify_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["notify_from"] = query.data
    await query.edit_message_text(
        f"Окно начинается в *{query.data}*.\nДо какого времени?",
        parse_mode="Markdown",
        reply_markup=kb([["14:00", "15:00", "16:00"], ["17:00", "18:00", "19:00"]])
    )
    return N_TO


async def got_notify_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["notify_to"] = query.data
    await query.edit_message_text(
        f"Окно: {context.user_data['notify_from']} – *{query.data}*.\n\n"
        "Сколько напоминаний в день?",
        parse_mode="Markdown",
        reply_markup=kb([[1, 2, 3]])
    )
    return N_COUNT


async def got_notify_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["notify_count"] = int(query.data)

    from database import get_user_id, save_notification_settings
    user_id = get_user_id(update.effective_user.id)
    save_notification_settings(user_id, {
        "time_from": context.user_data["notify_from"],
        "time_to":   context.user_data["notify_to"],
        "count":     context.user_data["notify_count"],
        "is_active": 1,
    })

    await query.edit_message_text(
        f"✅ *Уведомления настроены!*\n\n"
        f"Окно: {context.user_data['notify_from']} – {context.user_data['notify_to']}\n"
        f"Напоминаний в день: {context.user_data['notify_count']}\n\n"
        f"Плюс фиксированные:\n"
        f"• 22:00 — вечерний дневник\n"
        f"• Воскресенье — недельный отчёт",
        parse_mode="Markdown"
    )
    context.user_data.clear()
    return ConversationHandler.END


notify_conv = ConversationHandler(
    entry_points=[CommandHandler("notify", notify_start)],
    states={
        N_FROM:  [CallbackQueryHandler(got_notify_from)],
        N_TO:    [CallbackQueryHandler(got_notify_to)],
        N_COUNT: [CallbackQueryHandler(got_notify_count)],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: (
        u.message.reply_text("Отменил."), ConversationHandler.END
    )[-1])]
)
