"""
ege.py — полная система ЕГЭ.

Флоу настройки (один раз):
  1. Выбрать предметы
  2. Выбрать дни недели (общие или по предметам)
  3. Сохранить

Флоу занятия (каждый день):
  /ege или кнопка 📚 ЕГЭ
  → показывает предметы по расписанию на сегодня
  → выбор типа: новые / повтор / пробник / ошибки
  → если новые — выбрать номер задания
  → записать, показать прогресс
"""

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from database import (
    get_uid, save_ege_settings, get_ege_settings,
    get_today_ege_subjects, save_ege_task, mark_ege_task_done,
    get_ege_progress
)
from keyboards import ikb, main_kb

# Шаги настройки
ES_SUBJ, ES_SCHED_MODE, ES_DAYS, ES_DAYS_SUBJ = range(40, 44)
# Шаги занятия
ET_TYPE, ET_NUM = range(50, 52)

SUBJECTS_INFO = {
    "russian":     ("🇷🇺 Русский",     27),
    "math":        ("📐 Математика",    19),
    "informatics": ("💻 Информатика",   27),
    "physics":     ("⚛️ Физика",        30),
    "chemistry":   ("🧪 Химия",         34),
    "biology":     ("🌱 Биология",      28),
    "history":     ("📜 История",       21),
    "social":      ("🌍 Обществознание",25),
    "english":     ("🇬🇧 Английский",   44),
}

DAYS_RU = {"Mon":"Пн","Tue":"Вт","Wed":"Ср","Thu":"Чт","Fri":"Пт","Sat":"Сб","Sun":"Вс"}
DAYS_LIST = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

TASK_TYPES = [
    ("new",     "🆕 Новые задания"),
    ("repeat",  "🔄 Повтор старых"),
    ("trial",   "📝 Пробный вариант"),
    ("errors",  "🔍 Разбор ошибок"),
]


# ═══════════════════════════════════════════════════════════
# НАСТРОЙКА ЕГЭ
# ═══════════════════════════════════════════════════════════

def _subjects_kb(sel: set):
    rows = []
    for k, (lbl, _) in SUBJECTS_INFO.items():
        check = "✅ " if k in sel else ""
        rows.append([(check + lbl, f"es:{k}")])
    rows.append([("✅ Готово", "es:done")])
    return ikb(rows)


def _days_kb(sel: set):
    rows = []
    for i in range(0, len(DAYS_LIST), 3):
        row = []
        for d in DAYS_LIST[i:i+3]:
            check = "✅" if d in sel else "☐"
            row.append((f"{check} {DAYS_RU[d]}", f"ed:{d}"))
        rows.append(row)
    rows.append([("✅ Готово", "ed:done")])
    return ikb(rows)


async def setup_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["_es"] = set()
    ctx.user_data["_es_list"] = []
    ctx.user_data["_es_mode"] = None
    ctx.user_data["_es_days_sel"] = set()
    ctx.user_data["_es_days_idx"] = 0
    ctx.user_data["_es_schedule"] = {}
    await update.message.reply_text(
        "📚 *Настройка ЕГЭ*\n\n"
        "Шаг 1/3 — Какие предметы сдаёшь?\n"
        "_Выбери все нужные, потом нажми Готово_",
        parse_mode="Markdown",
        reply_markup=_subjects_kb(set())
    )
    return ES_SUBJ


async def got_es_subj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    val = q.data.split(":")[1]
    sel: set = ctx.user_data.setdefault("_es", set())

    if val == "done":
        if not sel:
            await q.answer("Выбери хотя бы один предмет!", show_alert=True)
            return ES_SUBJ
        await q.answer()
        ctx.user_data["_es_list"] = list(sel)
        await q.edit_message_text(
            "Шаг 2/3 — Как распределить дни?\n\n"
            "Выбери вариант:",
            reply_markup=ikb([
                [("📅 Любые дни для всех предметов", "esm:all")],
                [("🗓 Разные дни для каждого предмета", "esm:each")],
            ])
        )
        return ES_SCHED_MODE

    sel.discard(val) if val in sel else sel.add(val)
    await q.answer()
    await q.edit_message_reply_markup(_subjects_kb(sel))
    return ES_SUBJ


async def got_sched_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    mode = q.data.split(":")[1]
    ctx.user_data["_es_mode"] = mode
    ctx.user_data["_es_days_sel"] = set()
    ctx.user_data["_es_days_idx"] = 0
    ctx.user_data["_es_schedule"] = {}

    if mode == "all":
        await q.edit_message_text(
            "Шаг 3/3 — В какие дни будешь заниматься ЕГЭ?\n"
            "_Можно выбрать несколько_",
            parse_mode="Markdown",
            reply_markup=_days_kb(set())
        )
        return ES_DAYS
    else:
        return await _ask_days_for_subject(q, ctx)


async def _ask_days_for_subject(q, ctx):
    idx = ctx.user_data["_es_days_idx"]
    subj_list = ctx.user_data["_es_list"]
    if idx >= len(subj_list):
        return await _finish_setup(q, ctx)
    subj = subj_list[idx]
    lbl = SUBJECTS_INFO[subj][0]
    ctx.user_data["_es_days_sel"] = set()
    await q.edit_message_text(
        f"Шаг 3/3 — *{lbl}*\n\nВ какие дни будешь делать этот предмет?",
        parse_mode="Markdown",
        reply_markup=_days_kb(set())
    )
    return ES_DAYS_SUBJ


async def got_days_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    val = q.data.split(":")[1]
    sel: set = ctx.user_data.setdefault("_es_days_sel", set())

    if val == "done":
        if not sel:
            await q.answer("Выбери хотя бы один день!", show_alert=True)
            return ES_DAYS
        await q.answer()
        # Одинаковые дни для всех предметов
        for subj in ctx.user_data["_es_list"]:
            for day in sel:
                ctx.user_data["_es_schedule"].setdefault(day, [])
                if subj not in ctx.user_data["_es_schedule"][day]:
                    ctx.user_data["_es_schedule"][day].append(subj)
        return await _finish_setup(q, ctx)

    sel.discard(val) if val in sel else sel.add(val)
    await q.answer()
    await q.edit_message_reply_markup(_days_kb(sel))
    return ES_DAYS


async def got_days_each(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    val = q.data.split(":")[1]
    sel: set = ctx.user_data.setdefault("_es_days_sel", set())

    if val == "done":
        if not sel:
            await q.answer("Выбери хотя бы один день!", show_alert=True)
            return ES_DAYS_SUBJ
        await q.answer()
        idx = ctx.user_data["_es_days_idx"]
        subj = ctx.user_data["_es_list"][idx]
        for day in sel:
            ctx.user_data["_es_schedule"].setdefault(day, [])
            if subj not in ctx.user_data["_es_schedule"][day]:
                ctx.user_data["_es_schedule"][day].append(subj)
        ctx.user_data["_es_days_idx"] += 1
        ctx.user_data["_es_days_sel"] = set()  # сброс для следующего предмета
        return await _ask_days_for_subject(q, ctx)

    sel.discard(val) if val in sel else sel.add(val)
    await q.answer()
    await q.edit_message_reply_markup(_days_kb(sel))
    return ES_DAYS_SUBJ


async def _finish_setup(q, ctx):
    uid = get_uid(q.from_user.id)
    save_ege_settings(uid, ctx.user_data["_es_list"], ctx.user_data["_es_schedule"])

    subj_labels = [SUBJECTS_INFO[s][0] for s in ctx.user_data["_es_list"]]
    schedule_lines = []
    for day in DAYS_LIST:
        subjs = ctx.user_data["_es_schedule"].get(day, [])
        if subjs:
            names = ", ".join(SUBJECTS_INFO[s][0] for s in subjs)
            schedule_lines.append(f"{DAYS_RU[day]}: {names}")

    await q.edit_message_text(
        "✅ *Расписание ЕГЭ сохранено!*\n\n"
        f"Предметы: {', '.join(subj_labels)}\n\n"
        "*Расписание:*\n" + "\n".join(schedule_lines) + "\n\n"
        "_Теперь каждый день в разделе 📚 ЕГЭ будут появляться задания по расписанию._\n"
        "_Можно изменить в любой момент через /ege\\_setup_",
        parse_mode="Markdown"
    )
    ctx.user_data.clear()
    return ConversationHandler.END


setup_conv = ConversationHandler(
    entry_points=[CommandHandler("ege_setup", setup_start)],
    states={
        ES_SUBJ:      [CallbackQueryHandler(got_es_subj,   pattern="^es:")],
        ES_SCHED_MODE:[CallbackQueryHandler(got_sched_mode, pattern="^esm:")],
        ES_DAYS:      [CallbackQueryHandler(got_days_all,   pattern="^ed:")],
        ES_DAYS_SUBJ: [CallbackQueryHandler(got_days_each,  pattern="^ed:")],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    per_message=False,
)


# ═══════════════════════════════════════════════════════════
# ЗАНЯТИЕ ЕГЭ (ежедневно)
# ═══════════════════════════════════════════════════════════

def _task_nums_kb(subject: str, done_nums: set) -> list:
    """Кнопки номеров заданий для предмета."""
    max_num = SUBJECTS_INFO[subject][1]
    rows = []
    row = []
    for i in range(1, max_num + 1):
        check = "✅" if i in done_nums else str(i)
        row.append((check, f"en:{i}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("⬅️ Назад", "en:back")])
    return rows


async def ege_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update.effective_user.id)
    settings = get_ege_settings(uid)

    if not settings:
        await update.message.reply_text(
            "📚 *ЕГЭ*\n\nСначала настрой расписание!\n\n"
            "Нажми /ege\\_setup чтобы выбрать предметы и дни.",
            parse_mode="Markdown",
            reply_markup=main_kb()
        )
        return

    today_subjs = get_today_ege_subjects(uid)

    if not today_subjs:
        # Показываем все предметы для выбора вручную
        rows = [
            [(SUBJECTS_INFO[s][0], f"ege_s:{s}")]
            for s in settings["subjects"]
            if s in SUBJECTS_INFO
        ]
        await update.message.reply_text(
            "📚 *ЕГЭ*\n\nСегодня по расписанию ЕГЭ нет.\n\n"
            "Но можешь позаниматься любым предметом:",
            parse_mode="Markdown",
            reply_markup=ikb(rows)
        )
    else:
        rows = [
            [(SUBJECTS_INFO[s][0], f"ege_s:{s}")]
            for s in today_subjs
            if s in SUBJECTS_INFO
        ]
        await update.message.reply_text(
            "📚 *ЕГЭ — сегодня по расписанию:*\n\n"
            "Выбери предмет для занятия:",
            parse_mode="Markdown",
            reply_markup=ikb(rows)
        )


async def ege_pick_subject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    subj = q.data.split(":")[1]
    ctx.user_data["_ege_subj"] = subj
    lbl = SUBJECTS_INFO[subj][0]

    rows = [[(tl, f"et:{tk}")] for tk, tl in TASK_TYPES]
    await q.edit_message_text(
        f"*{lbl}*\n\nКакой тип задач сегодня?",
        parse_mode="Markdown",
        reply_markup=ikb(rows)
    )
    return ET_TYPE


async def got_task_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    task_type = q.data.split(":")[1]
    ctx.user_data["_ege_type"] = task_type
    subj = ctx.user_data["_ege_subj"]
    lbl = SUBJECTS_INFO[subj][0]

    if task_type == "new":
        uid = get_uid(q.from_user.id)
        progress = get_ege_progress(uid, subj)
        done_nums = set(progress.keys())
        max_num = SUBJECTS_INFO[subj][1]

        await q.edit_message_text(
            f"*{lbl}* — Новые задания\n\n"
            f"Выбери номер задания (✅ = уже делал раньше):\n"
            f"Всего заданий: {max_num}",
            parse_mode="Markdown",
            reply_markup=ikb(_task_nums_kb(subj, done_nums))
        )
        return ET_NUM
    else:
        # Не новые — сохраняем сразу
        uid = get_uid(q.from_user.id)
        type_names = dict(TASK_TYPES)
        save_ege_task(uid, subj, task_type)

        tips = {
            "repeat": "🔄 *Циклическое повторение* — главный метод стобалльников!\nВозвращайся к пройденному через 1, 3, 7 дней.",
            "trial":  "📝 *Пробный вариант* — отличная тренировка!\nПосле решения разбери каждую ошибку детально.",
            "errors": "🔍 *Разбор ошибок* — самое ценное занятие.\nФокусируйся на том, что проседает больше всего.",
        }

        await q.edit_message_text(
            f"✅ *Записал!*\n\n"
            f"{lbl} → {type_names.get(task_type, task_type)}\n\n"
            f"{tips.get(task_type, '')}\n\n"
            f"Когда закончишь — отметь как выполненное в «✅ Отметить»",
            parse_mode="Markdown"
        )
        ctx.user_data.clear()
        return ConversationHandler.END


async def got_task_num(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    val = q.data.split(":")[1]

    if val == "back":
        subj = ctx.user_data["_ege_subj"]
        lbl = SUBJECTS_INFO[subj][0]
        rows = [[(tl, f"et:{tk}")] for tk, tl in TASK_TYPES]
        await q.edit_message_text(
            f"*{lbl}*\n\nКакой тип задач сегодня?",
            parse_mode="Markdown",
            reply_markup=ikb(rows)
        )
        return ET_TYPE

    num = int(val)
    subj = ctx.user_data["_ege_subj"]
    lbl = SUBJECTS_INFO[subj][0]
    uid = get_uid(q.from_user.id)

    save_ege_task(uid, subj, "new", num)
    mark_ege_task_done(uid, subj, num)

    progress = get_ege_progress(uid, subj)
    times = progress.get(num, {}).get("times", 1)

    tip = ""
    if times == 1:
        tip = "\n\n💡 Первый раз — просто разберись, не торопись."
    elif times == 2:
        tip = "\n\n💡 Второй раз — попробуй решить самостоятельно до подсказок."
    elif times >= 3:
        tip = f"\n\n🔥 Ты уже делал это задание {times} раз — отличное повторение!"

    await q.edit_message_text(
        f"✅ *Записал задание №{num}*\n"
        f"Предмет: {lbl}{tip}\n\n"
        f"_Используй метод активного запоминания: реши, затем закрой и воспроизведи по памяти._",
        parse_mode="Markdown"
    )
    ctx.user_data.clear()
    return ConversationHandler.END


ege_session_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(ege_pick_subject, pattern="^ege_s:"),
    ],
    states={
        ET_TYPE: [CallbackQueryHandler(got_task_type, pattern="^et:")],
        ET_NUM:  [CallbackQueryHandler(got_task_num,  pattern="^en:")],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    per_message=False,
)


async def ege_progress_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показывает прогресс по всем предметам."""
    uid = get_uid(update.effective_user.id)
    settings = get_ege_settings(uid)
    if not settings:
        await update.message.reply_text("Настрой ЕГЭ сначала: /ege_setup")
        return

    lines = ["📊 *Прогресс по заданиям ЕГЭ*\n"]
    for subj in settings["subjects"]:
        if subj not in SUBJECTS_INFO:
            continue
        lbl, max_num = SUBJECTS_INFO[subj]
        progress = get_ege_progress(uid, subj)
        done = len(progress)
        pct = round(done / max_num * 100)
        bar_w = 10
        filled = round(pct / 100 * bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)
        lines.append(f"{lbl}\n{bar} {done}/{max_num} заданий ({pct}%)")

        # Показываем какие задания делал
        if progress:
            done_nums = sorted(progress.keys())
            nums_str = ", ".join(str(n) for n in done_nums[:15])
            if len(done_nums) > 15:
                nums_str += "..."
            lines.append(f"  ✅ Сделаны: {nums_str}")
        lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown",
                                    reply_markup=main_kb())
