from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from database import get_uid, save_plan, get_today_plans, toggle_plan
from keyboards import ikb, main_kb

P_SUBJ, P_TYPE, P_CUSTOM_TEXT, P_CUSTOM_REMIND = range(20, 24)

SUBJECTS = {
    "python":  ("🐍 Python",  ["Теория", "Практика", "Проект", "Задачи"]),
    "sport":   ("🏃 Спорт",   ["Тренировка", "Прогулка", "Растяжка"]),
    "reading": ("📖 Чтение",  ["Художественное", "Нон-фикшн", "Учёба"]),
    "other":   ("📌 Другое",  []),
}
LABELS = {k: v[0] for k, v in SUBJECTS.items()}
LABELS["custom"] = "📝 Своя задача"


def _subj_kb(sel: set):
    rows = [
        [("✅ " + lbl if k in sel else lbl, f"ps:{k}")]
        for k, (lbl, _) in SUBJECTS.items()
    ]
    rows.append([("📝 + Своя задача", "ps:custom")])
    rows.append([("✅ Готово", "ps:done")])
    return ikb(rows)


async def plan_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["_ps"] = set()
    ctx.user_data["_ptasks"] = {}
    ctx.user_data["_custom_tasks"] = []
    await update.message.reply_text(
        "📋 *План на день*\n\nЧем занимаешься сегодня?\n"
        "_Выбери из списка или добавь свою задачу_",
        parse_mode="Markdown",
        reply_markup=_subj_kb(set())
    )
    return P_SUBJ


async def got_subj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    val = q.data.split(":")[1]
    sel: set = ctx.user_data["_ps"]

    if val == "custom":
        await q.edit_message_text(
            "📝 *Своя задача*\n\nНапиши название задачи:",
            parse_mode="Markdown"
        )
        return P_CUSTOM_TEXT

    if val == "done":
        if not sel and not ctx.user_data.get("_custom_tasks"):
            await q.answer("Выбери хотя бы одно направление!", show_alert=True)
            return P_SUBJ
        ctx.user_data["_plist"] = list(sel)
        ctx.user_data["_pidx"] = 0
        if sel:
            return await _ask_type(q, ctx)
        else:
            return await _save_all(q, ctx)

    sel.discard(val) if val in sel else sel.add(val)
    await q.edit_message_reply_markup(_subj_kb(sel))
    return P_SUBJ


async def got_custom_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["_current_custom"] = update.message.text
    await update.message.reply_text(
        f"📝 Задача: *{update.message.text}*\n\n"
        "Поставить напоминание?",
        parse_mode="Markdown",
        reply_markup=ikb([
            [("⏰ Да, выбрать время", "cr:yes")],
            [("Без напоминания", "cr:no")],
        ])
    )
    return P_CUSTOM_REMIND


async def got_custom_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    val = q.data.split(":")[1]

    if val == "yes":
        await q.edit_message_text(
            "В какое время напомнить?",
            reply_markup=ikb([
                [("9:00", "ct:09:00"), ("10:00", "ct:10:00"), ("11:00", "ct:11:00")],
                [("12:00", "ct:12:00"), ("13:00", "ct:13:00"), ("14:00", "ct:14:00")],
                [("15:00", "ct:15:00"), ("16:00", "ct:16:00"), ("17:00", "ct:17:00")],
                [("18:00", "ct:18:00"), ("19:00", "ct:19:00"), ("20:00", "ct:20:00")],
            ])
        )
        return P_CUSTOM_REMIND

    if val == "no":
        ctx.user_data["_custom_tasks"].append({
            "text": ctx.user_data["_current_custom"],
            "remind": None
        })
        return await _back_to_menu(q, ctx)

    # Выбрано время
    time_str = q.data.replace("ct:", "")
    ctx.user_data["_custom_tasks"].append({
        "text": ctx.user_data["_current_custom"],
        "remind": time_str
    })
    await q.edit_message_text(
        f"✅ Задача добавлена с напоминанием в {time_str}"
    )
    return await _back_to_menu_msg(q, ctx)


async def _back_to_menu(q, ctx):
    await q.edit_message_text(
        "Добавлено! Добавить ещё?",
        reply_markup=_subj_kb(ctx.user_data.get("_ps", set()))
    )
    return P_SUBJ


async def _back_to_menu_msg(q, ctx):
    # Используется когда уже показали сообщение
    await q.answer()
    return P_SUBJ


async def _ask_type(q, ctx):
    idx = ctx.user_data["_pidx"]
    subj_list = ctx.user_data["_plist"]
    if idx >= len(subj_list):
        return await _save_all(q, ctx)
    subj = subj_list[idx]
    lbl, types = SUBJECTS[subj]
    total = len(subj_list)

    if not types:  # "Другое" — без типа
        ctx.user_data["_ptasks"][subj] = "—"
        ctx.user_data["_pidx"] += 1
        return await _ask_type(q, ctx)

    rows = [[(t, f"pt:{t}")] for t in types]
    rows.append([("⏭ Пропустить", "pt:__skip__")])
    await q.edit_message_text(
        f"*{lbl}* ({idx+1}/{total}) — тип задачи:",
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
    return await _save_all(q, ctx)


async def _save_all(q, ctx):
    uid = get_uid(q.from_user.id)
    tasks = ctx.user_data.get("_ptasks", {})
    custom = ctx.user_data.get("_custom_tasks", [])

    for subj, ttype in tasks.items():
        save_plan(uid, subj, ttype)

    for ct in custom:
        save_plan(uid, "custom", ct["text"], is_custom=1, remind_at=ct.get("remind"))

    lines = ["✅ *План на день сохранён!*\n"]
    for subj, ttype in tasks.items():
        lines.append(f"{LABELS.get(subj, subj)} — {ttype}")
    for ct in custom:
        remind = f" ⏰{ct['remind']}" if ct.get("remind") else ""
        lines.append(f"📝 {ct['text']}{remind}")
    lines.append("\n_Вечером отметь что выполнил_ 👇")

    await q.edit_message_text("\n".join(lines), parse_mode="Markdown")
    ctx.user_data.clear()
    return ConversationHandler.END


plan_conv = ConversationHandler(
    entry_points=[
        CommandHandler("plan", plan_start),
        MessageHandler(filters.Regex("^📋 План на день$"), plan_start),
    ],
    states={
        P_SUBJ:         [CallbackQueryHandler(got_subj,         pattern="^ps:")],
        P_TYPE:         [CallbackQueryHandler(got_type,         pattern="^pt:")],
        P_CUSTOM_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_custom_text)],
        P_CUSTOM_REMIND:[
            CallbackQueryHandler(got_custom_remind, pattern="^(cr:|ct:)"),
        ],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    per_message=False,
)


# ── Отметить выполнено ────────────────────────────────────

def _done_kb(plans: list[dict]):
    rows = []
    for p in plans:
        subj = p["subject"]
        lbl = LABELS.get(subj, subj)
        if subj == "custom":
            lbl = f"📝 {p.get('task_type','')}"
        ttype = p.get("task_type", "")
        check = "✅" if p["done"] else "☐"
        toggle = "0" if p["done"] else "1"
        display = f"{check} {lbl}" if subj == "custom" else f"{check} {lbl} — {ttype}"
        rows.append([(display, f"td:{p['id']}:{toggle}")])
    rows.append([("💾 Сохранить", "td:save:0")])
    return ikb(rows)


async def done_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update.effective_user.id)
    plans = get_today_plans(uid)
    if not plans:
        await update.message.reply_text(
            "Сегодня план пустой.\n\nСначала: «📋 План на день»",
            reply_markup=main_kb()
        )
        return
    done_c = sum(1 for p in plans if p["done"])
    await update.message.reply_text(
        f"✅ *Выполнено: {done_c}/{len(plans)}*\n\nОтмечай что сделал:",
        parse_mode="Markdown",
        reply_markup=_done_kb(plans)
    )


async def toggle_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    if parts[1] == "save":
        await q.edit_message_text("💾 *Сохранено!* 💪", parse_mode="Markdown")
        return
    plan_id = int(parts[1])
    new_done = int(parts[2])
    toggle_plan(plan_id, new_done)
    uid = get_uid(q.from_user.id)
    plans = get_today_plans(uid)
    done_c = sum(1 for p in plans if p["done"])
    await q.edit_message_text(
        f"✅ *Выполнено: {done_c}/{len(plans)}*\n\nОтмечай что сделал:",
        parse_mode="Markdown",
        reply_markup=_done_kb(plans)
    )


async def today_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update.effective_user.id)
    plans = get_today_plans(uid)
    if not plans:
        await update.message.reply_text(
            "Сегодня план пустой. Нажми «📋 План на день»",
            reply_markup=main_kb()
        )
        return
    done_c = sum(1 for p in plans if p["done"])
    pct = round(done_c / len(plans) * 100)
    lines = [f"📊 *Сегодня — {done_c}/{len(plans)} ({pct}%)*\n"]
    for p in plans:
        subj = p["subject"]
        check = "✅" if p["done"] else "☐"
        if subj == "custom":
            remind = f" ⏰{p['remind_at']}" if p.get("remind_at") else ""
            lines.append(f"{check} 📝 {p.get('task_type','')}{remind}")
        else:
            lbl = LABELS.get(subj, subj)
            lines.append(f"{check} {lbl} — {p.get('task_type','')}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown",
                                    reply_markup=main_kb())
