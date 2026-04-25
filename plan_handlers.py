"""
plan_handlers.py — трекер задач на день.

Кнопки в главном меню:
  📋 План на день   → /plan
  ✅ Отметить       → /done
  📊 Сегодня        → /today
"""

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from database import get_user_id
from plan_database import save_plan, get_today_plan, mark_done

# ── Шаги ConversationHandler ──────────────────────────────
P_SUBJECTS, P_TASKTYPE = range(30, 32)

# ── Направления и их типы задач ──────────────────────────
SUBJECTS = {
    "ege":     ("📚 ЕГЭ",       ["Новые задания", "Повтор старых", "Пробный вариант", "Разбор ошибок"]),
    "python":  ("🐍 Python",    ["Теория", "Практика", "Работа над проектом", "Задачи/упражнения"]),
    "sport":   ("🏃 Спорт",     ["Тренировка", "Прогулка", "Растяжка"]),
    "reading": ("📖 Чтение",    ["Художественное", "Нон-фикшн", "Учебный материал"]),
}

SUBJECT_LABELS = {k: v[0] for k, v in SUBJECTS.items()}


# ═══════════════════════════════════════════════════════════
# ГЛАВНОЕ МЕНЮ (ReplyKeyboard — постоянные кнопки внизу)
# ═══════════════════════════════════════════════════════════

def main_menu() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура внизу экрана."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📋 План на день"), KeyboardButton("✅ Выполнено")],
            [KeyboardButton("📊 Сегодня"),      KeyboardButton("📈 Статистика")],
            [KeyboardButton("🌅 Утро"),          KeyboardButton("🌙 Вечер")],
        ],
        resize_keyboard=True,       # кнопки компактные
        one_time_keyboard=False     # меню не скрывается после нажатия
    )


# ── Вспомогалка: inline-клавиатура ───────────────────────

def ikb(rows: list[list[tuple]]) -> InlineKeyboardMarkup:
    """
    rows — список строк, каждая строка — список (текст, callback_data).
    Пример: ikb([[("Да", "yes"), ("Нет", "no")]])
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text, callback_data=data) for text, data in row]
        for row in rows
    ])


# ═══════════════════════════════════════════════════════════
# /plan — планирование дня
# ═══════════════════════════════════════════════════════════

async def plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 1: выбор направлений (мультивыбор)."""
    context.user_data["plan_selected"] = set()  # сбрасываем выбор

    await update.message.reply_text(
        "📋 *План на день*\n\nЧем планируешь заниматься? "
        "_(выбери одно или несколько, потом нажми ✅ Готово)_",
        parse_mode="Markdown",
        reply_markup=_subjects_kb(set())
    )
    return P_SUBJECTS


def _subjects_kb(selected: set) -> InlineKeyboardMarkup:
    """Клавиатура выбора направлений с мультивыбором."""
    rows = []
    for key, (label, _) in SUBJECTS.items():
        check = "✅ " if key in selected else ""
        rows.append([(check + label, f"subj_{key}")])
    rows.append([("✅ Готово", "subj_done")])
    return ikb(rows)


async def got_subjects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на направления и кнопку Готово."""
    query = update.callback_query
    await query.answer()

    selected: set = context.user_data.get("plan_selected", set())

    if query.data == "subj_done":
        if not selected:
            await query.answer("Выбери хотя бы одно направление!", show_alert=True)
            return P_SUBJECTS

        # Переходим к выбору типа задачи для первого направления
        context.user_data["plan_subjects"] = list(selected)
        context.user_data["plan_current_idx"] = 0
        context.user_data["plan_tasks"] = {}

        return await _ask_task_type(query, context)

    else:
        # Переключаем выбор направления
        key = query.data.replace("subj_", "")
        if key in selected:
            selected.discard(key)
        else:
            selected.add(key)
        context.user_data["plan_selected"] = selected

        await query.edit_message_reply_markup(_subjects_kb(selected))
        return P_SUBJECTS


async def _ask_task_type(query, context: ContextTypes.DEFAULT_TYPE):
    """Спрашивает тип задачи для текущего направления."""
    subjects = context.user_data["plan_subjects"]
    idx = context.user_data["plan_current_idx"]
    subject_key = subjects[idx]

    label, task_types = SUBJECTS[subject_key]
    total = len(subjects)

    rows = [[(t, f"task_{t}")] for t in task_types]
    rows.append([("⏭ Пропустить", "task_skip")])

    await query.edit_message_text(
        f"*{label}* ({idx+1}/{total})\n\nКакой тип задачи?",
        parse_mode="Markdown",
        reply_markup=ikb(rows)
    )
    return P_TASKTYPE


async def got_task_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает тип задачи и переходит к следующему направлению."""
    query = update.callback_query
    await query.answer()

    subjects = context.user_data["plan_subjects"]
    idx = context.user_data["plan_current_idx"]
    subject_key = subjects[idx]

    if query.data != "task_skip":
        task_type = query.data.replace("task_", "")
        context.user_data["plan_tasks"][subject_key] = task_type

    # Переходим к следующему направлению
    context.user_data["plan_current_idx"] = idx + 1
    next_idx = context.user_data["plan_current_idx"]

    if next_idx < len(subjects):
        return await _ask_task_type(query, context)

    # Все направления выбраны — сохраняем
    return await _save_plan(query, context)


async def _save_plan(query, context: ContextTypes.DEFAULT_TYPE):
    """Финальное сохранение плана."""
    user_id = get_user_id(query.from_user.id)
    tasks = context.user_data.get("plan_tasks", {})

    for subject_key, task_type in tasks.items():
        save_plan(user_id, subject_key, task_type)

    # Формируем красивый итог
    lines = ["✅ *План на сегодня сохранён!*\n"]
    for subject_key, task_type in tasks.items():
        label = SUBJECT_LABELS[subject_key]
        lines.append(f"{label} — {task_type}")

    lines.append("\n_Вечером отметь что выполнил — кнопка «✅ Выполнено»_")

    await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END


plan_conv = ConversationHandler(
    entry_points=[
        CommandHandler("plan", plan_start),
        MessageHandler(filters.Regex("^📋 План на день$"), plan_start),
    ],
    states={
        P_SUBJECTS: [CallbackQueryHandler(got_subjects, pattern="^subj_")],
        P_TASKTYPE: [CallbackQueryHandler(got_task_type, pattern="^task_")],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
)


# ═══════════════════════════════════════════════════════════
# /done — отметить выполненное
# ═══════════════════════════════════════════════════════════

async def done_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает план дня с кнопками для отметки выполнения."""
    user_id = get_user_id(update.effective_user.id)
    tasks = get_today_plan(user_id)

    if not tasks:
        await update.message.reply_text(
            "📋 Сегодня нет плана.\n\nСначала создай его — кнопка «📋 План на день»"
        )
        return

    lines = ["✅ *Отметь что выполнил сегодня:*\n"]
    rows = []
    for t in tasks:
        label = SUBJECT_LABELS.get(t["subject"], t["subject"])
        task_type = t.get("task_type", "")
        is_done = t["done"] == 1
        check = "✅" if is_done else "☐"
        lines.append(f"{check} {label} — {task_type}")

        toggle = "undone" if is_done else "done"
        rows.append([(f"{check} {label}", f"toggle_{toggle}_{t['subject']}")])

    rows.append([("💾 Сохранить", "done_save")])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=ikb(rows)
    )


async def toggle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключает статус задачи по нажатию кнопки."""
    query = update.callback_query
    await query.answer()

    if query.data == "done_save":
        await query.edit_message_text(
            "💾 *Сохранено!* Молодец 💪",
            parse_mode="Markdown"
        )
        return

    # Парсим: toggle_done_python или toggle_undone_ege
    parts = query.data.split("_", 2)   # ['toggle', 'done'/'undone', 'subject']
    action = parts[1]
    subject = parts[2]

    user_id = get_user_id(query.from_user.id)
    mark_done(user_id, subject, done=1 if action == "done" else 0)

    # Перестраиваем сообщение с обновлёнными статусами
    tasks = get_today_plan(user_id)
    lines = ["✅ *Отметь что выполнил сегодня:*\n"]
    rows = []
    for t in tasks:
        label = SUBJECT_LABELS.get(t["subject"], t["subject"])
        task_type = t.get("task_type", "")
        is_done = t["done"] == 1
        check = "✅" if is_done else "☐"
        lines.append(f"{check} {label} — {task_type}")

        toggle = "undone" if is_done else "done"
        rows.append([(f"{check} {label}", f"toggle_{toggle}_{t['subject']}")])

    rows.append([("💾 Сохранить", "done_save")])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=ikb(rows)
    )


done_handler = MessageHandler(
    filters.Regex("^✅ Выполнено$"), done_start
)
done_toggle_handler = CallbackQueryHandler(
    toggle_done, pattern="^(toggle_|done_save)"
)


# ═══════════════════════════════════════════════════════════
# /today — посмотреть план
# ═══════════════════════════════════════════════════════════

async def today_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает план на сегодня (только просмотр)."""
    user_id = get_user_id(update.effective_user.id)
    tasks = get_today_plan(user_id)

    if not tasks:
        await update.message.reply_text(
            "📋 Сегодня план пустой.\n\nНажми «📋 План на день» чтобы создать его."
        )
        return

    done_count = sum(1 for t in tasks if t["done"] == 1)
    total = len(tasks)
    pct = round(done_count / total * 100)

    lines = [f"📊 *Сегодня — {done_count}/{total} выполнено ({pct}%)*\n"]
    for t in tasks:
        label = SUBJECT_LABELS.get(t["subject"], t["subject"])
        check = "✅" if t["done"] == 1 else "☐"
        lines.append(f"{check} {label} — {t.get('task_type', '')}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


today_handler = MessageHandler(
    filters.Regex("^📊 Сегодня$"), today_start
)
