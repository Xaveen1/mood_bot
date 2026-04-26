from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from database import get_uid, save_plan, get_today_plans, toggle_plan
from keyboards import ikb, main_kb

P_SUBJ, P_TYPE = range(20, 22)

SUBJECTS = {
    "ege":     ("📚 ЕГЭ",    ["Новые задания", "Повтор старых", "Пробный вариант", "Разбор ошибок"]),
    "python":  ("🐍 Python", ["Теория", "Практика", "Работа над проектом", "Задачи"]),
    "sport":   ("🏃 Спорт",  ["Тренировка", "Прогулка", "Растяжка"]),
    "reading": ("📖 Чтение", ["Художественное", "Нон-фикшн", "Учёба"]),
}
LABELS = {k: v[0] for k, v in SUBJECTS.items()}


def _subj_kb(sel: set):
    rows = [
        [("✅ " + lbl if k in sel else lbl, f"ps:{k}")]
        for k, (lbl, _) in SUBJECTS.items()
    ]
    rows.append([("✅ Готово", "ps:done")])
    return ikb(rows)


async def plan_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["_ps"] = set()
    ctx.user_data["_ptasks"] = {}
    ctx.user_data["_pidx"] = 0
    await update.message.reply_text(
        "📋 *План на день*\n\nЧем планируешь заниматься?\n"
        "_Выбери направления, потом нажми Готово_",
        parse_mode="Markdown",
        reply_markup=_subj_kb(set())
    )
    return P_SUBJ


async def got_subj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    val = q.data.split(":")[1]
    sel: set = ctx.user_data["_ps"]

    if val == "done":
        if not sel:
            await q.answer("Выбери хотя бы одно направление!", show_alert=True)
            return P_SUBJ
        ctx.user_data["_plist"] = list(sel)
        ctx.user_data["_pidx"] = 0
        return await _ask_type(q, ctx)

    sel.discard(val) if val in sel else sel.add(val)
    await q.edit_message_reply_markup(_subj_kb(sel))
    return P_SUBJ


async def _ask_type(q, ctx):
    idx = ctx.user_data["_pidx"]
    subj = ctx.user_data["_plist"][idx]
    lbl, types = SUBJECTS[subj]
    total = len(ctx.user_data["_plist"])
    rows = [[(t, f"pt:{t}")] for t in types]
    rows.append([("⏭ Пропустить", "pt:__skip__")])
    await q.edit_message_text(
        f"*{lbl}* ({idx+1}/{total})\n\nКакой тип задачи сегодня?",
        parse_mode="Markdown",
        reply_markup=ikb(rows)
    )
    return P_TYPE


async def got_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    val = q.data.split(":", 1)[1]
    idx = ctx.user_data["_pidx"]
    subj = ctx.user_data["_plist"][idx]

    if val != "__skip__":
        ctx.user_data["_ptasks"][subj] = val

    ctx.user_data["_pidx"] += 1
    if ctx.user_data["_pidx"] < len(ctx.user_data["_plist"]):
        return await _ask_type(q, ctx)

    # Сохраняем всё
    uid = get_uid(q.from_user.id)
    tasks = ctx.user_data["_ptasks"]
    for subj, ttype in tasks.items():
        save_plan(uid, subj, ttype)

    lines = ["✅ *План сохранён!*\n"]
    for subj, ttype in tasks.items():
        lines.append(f"{LABELS[subj]} — {ttype}")
    lines.append("\n_Вечером отметь что выполнил_ 👇")

    await q.edit_message_text("\n".join(lines), parse_mode="Markdown")
    ctx.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменил.", reply_markup=main_kb())
    ctx.user_data.clear()
    return ConversationHandler.END


plan_conv = ConversationHandler(
    entry_points=[
        CommandHandler("plan", plan_start),
        MessageHandler(filters.Regex("^📋 План на день$"), plan_start),
    ],
    states={
        P_SUBJ: [CallbackQueryHandler(got_subj, pattern="^ps:")],
        P_TYPE: [CallbackQueryHandler(got_type, pattern="^pt:")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False,
)


# ── Отметить выполнено ────────────────────────────────────

def _done_kb(plans: list[dict]):
    rows = []
    for p in plans:
        lbl = LABELS.get(p["subject"], p["subject"])
        ttype = p.get("task_type", "")
        check = "✅" if p["done"] else "☐"
        toggle = "0" if p["done"] else "1"
        rows.append([(f"{check} {lbl} — {ttype}", f"td:{p['id']}:{toggle}")])
    rows.append([("💾 Сохранить", "td:save:0")])
    return ikb(rows)


async def done_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update.effective_user.id)
    plans = get_today_plans(uid)
    if not plans:
        await update.message.reply_text(
            "📋 Сегодня нет плана.\n\nСначала создай — кнопка «📋 План на день»",
            reply_markup=main_kb()
        )
        return
    done_c = sum(1 for p in plans if p["done"])
    await update.message.reply_text(
        f"✅ *Выполнено сегодня: {done_c}/{len(plans)}*\n\n"
        f"Нажимай на задачи чтобы отметить:",
        parse_mode="Markdown",
        reply_markup=_done_kb(plans)
    )


async def toggle_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    if parts[1] == "save":
        await q.edit_message_text("💾 *Сохранено!* Так держать 💪", parse_mode="Markdown")
        return
    plan_id = int(parts[1])
    new_done = int(parts[2])
    toggle_plan(plan_id, new_done)

    uid = get_uid(q.from_user.id)
    plans = get_today_plans(uid)
    done_c = sum(1 for p in plans if p["done"])
    await q.edit_message_text(
        f"✅ *Выполнено сегодня: {done_c}/{len(plans)}*\n\n"
        f"Нажимай на задачи чтобы отметить:",
        parse_mode="Markdown",
        reply_markup=_done_kb(plans)
    )


# ── Мой день (просмотр) ───────────────────────────────────

async def today_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update.effective_user.id)
    plans = get_today_plans(uid)
    if not plans:
        await update.message.reply_text(
            "📋 Сегодня план пустой.\n\nНажми «📋 План на день» чтобы создать.",
            reply_markup=main_kb()
        )
        return
    done_c = sum(1 for p in plans if p["done"])
    pct = round(done_c / len(plans) * 100)
    lines = [f"📊 *Сегодня — {done_c}/{len(plans)} ({pct}%)*\n"]
    for p in plans:
        lbl = LABELS.get(p["subject"], p["subject"])
        check = "✅" if p["done"] else "☐"
        lines.append(f"{check} {lbl} — {p.get('task_type','')}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown",
                                    reply_markup=main_kb())
