from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from database import get_uid, save_evening
from keyboards import score_kb, yes_no_kb, ikb, main_kb

MOOD, ENERGY, SPORT, WATER, HABITS, SOCIAL, NOTE = range(7)

HABITS_LIST = [
    ("meditation", "🧘 Медитация"),
    ("reading",    "📚 Чтение"),
    ("food_ok",    "🥗 Нормально поел"),
]


def _habits_kb(selected: set):
    rows = [
        [("✅ " + lbl if k in selected else "☐ " + lbl, f"hab:{k}")]
        for k, lbl in HABITS_LIST
    ]
    rows.append([("✅ Готово", "hab:done")])
    return ikb(rows)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌙 *Вечерний дневник*\n\n"
        "Как *настроение* сегодня?\n1 😞  2 😕  3 😐  4 🙂  5 😄",
        parse_mode="Markdown",
        reply_markup=score_kb("mood")
    )
    return MOOD


async def got_mood(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["mood"] = int(q.data.split(":")[1])
    await update.message.reply_text(
        "Уровень *энергии* весь день?\n1 🪫  2 😴  3 ⚡  4 🔋  5 🚀",
        parse_mode="Markdown",
        reply_markup=score_kb("nrg")
    )
    return ENERGY


async def got_energy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["energy"] = int(q.data.split(":")[1])
    await update.message.reply_text(
        "Был *спорт или прогулка*?",
        parse_mode="Markdown",
        reply_markup=yes_no_kb("sp:1", "sp:0", "Да 🏃", "Нет 🛋")
    )
    return SPORT


async def got_sport(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["sport"] = int(q.data.split(":")[1])
    await update.message.reply_text(
        "Сколько стаканов *воды* выпил?",
        parse_mode="Markdown",
        reply_markup=ikb([
            [("0–2 💧", "wat:1"), ("3–4 💧💧", "wat:3")],
            [("5–6 💧💧💧", "wat:5"), ("7–8 💧💧💧💧", "wat:7"), ("8+ 🌊", "wat:9")],
        ])
    )
    return WATER


async def got_water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["water"] = int(q.data.split(":")[1])
    ctx.user_data["_habits"] = set()
    await update.message.reply_text(
        "Что выполнил сегодня?\n_Выбери всё подходящее → Готово_",
        parse_mode="Markdown",
        reply_markup=_habits_kb(set())
    )
    return HABITS


async def got_habits(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    val = q.data.split(":")[1]
    sel: set = ctx.user_data.setdefault("_habits", set())

    if val == "done":
        for k, _ in HABITS_LIST:
            ctx.user_data[k] = 1 if k in sel else 0
        await update.message.reply_text(
            "Было *живое общение* с людьми?",
            parse_mode="Markdown",
            reply_markup=yes_no_kb("soc:1", "soc:0", "Да 👥", "Нет 🏠")
        )
        return SOCIAL

    sel.discard(val) if val in sel else sel.add(val)
    await q.edit_message_reply_markup(_habits_kb(sel))
    return HABITS


async def got_social(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["social"] = int(q.data.split(":")[1])
    await update.message.reply_text(
        "Заметка о дне ✏️\n\n"
        "Напиши что угодно — или /skip чтобы пропустить.",
        parse_mode="Markdown"
    )
    return NOTE


async def got_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["note"] = update.message.text
    await _finish(update, ctx)
    return ConversationHandler.END


async def skip_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["note"] = None
    await _finish(update, ctx)
    return ConversationHandler.END


async def _finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update.effective_user.id)
    ctx.user_data.pop("_habits", None)
    save_evening(uid, ctx.user_data)

    mood = ctx.user_data.get("mood", 0)
    energy = ctx.user_data.get("energy", 0)
    sport = "✅" if ctx.user_data.get("sport") else "❌"
    med = "✅" if ctx.user_data.get("meditation") else "❌"
    read = "✅" if ctx.user_data.get("reading") else "❌"
    stars = lambda n: "⭐" * n + "☆" * (5 - n)

    await update.message.reply_text(
        f"🌙 *День записан!*\n\n"
        f"😊 Настроение: {stars(mood)}\n"
        f"⚡ Энергия:    {stars(energy)}\n"
        f"🏃 Спорт: {sport}  🧘 Медитация: {med}  📚 Чтение: {read}\n\n"
        f"_Данные идут в аналитику — завтра будет видно динамику_ 📊",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )
    ctx.user_data.clear()


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменил.", reply_markup=main_kb())
    ctx.user_data.clear()
    return ConversationHandler.END


evening_conv = ConversationHandler(
    entry_points=[
        CommandHandler("evening", start),
        MessageHandler(filters.Regex("^🌙 Вечерний дневник$"), start),
    ],
    states={
        MOOD:   [CallbackQueryHandler(got_mood,   pattern="^mood:")],
        ENERGY: [CallbackQueryHandler(got_energy, pattern="^nrg:")],
        SPORT:  [CallbackQueryHandler(got_sport,  pattern="^sp:")],
        WATER:  [CallbackQueryHandler(got_water,  pattern="^wat:")],
        HABITS: [CallbackQueryHandler(got_habits, pattern="^hab:")],
        SOCIAL: [CallbackQueryHandler(got_social, pattern="^soc:")],
        NOTE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, got_note),
            CommandHandler("skip", skip_note),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=True,
)
