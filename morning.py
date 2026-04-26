from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from database import get_uid, save_morning
from keyboards import score_kb, yes_no_kb, ikb, main_kb

SLEEP_H, SLEEP_Q, DREAMS, PHONE = range(4)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    await msg.reply_text(
        "🌅 *Утренний опрос* — 4 быстрых вопроса\n\n"
        "Сколько часов ты спал?",
        parse_mode="Markdown",
        reply_markup=ikb([
            [("5ч", "slh:5"), ("6ч", "slh:6"), ("7ч", "slh:7")],
            [("8ч", "slh:8"), ("9ч", "slh:9"), ("10+ч", "slh:10")],
        ])
    )
    return SLEEP_H


async def got_sleep_h(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["sleep_h"] = float(q.data.split(":")[1])
    await q.edit_message_text(
        "Как оцениваешь *качество сна*?\n\n1 — ужасно, 5 — отлично",
        parse_mode="Markdown",
        reply_markup=score_kb("slq")
    )
    return SLEEP_Q


async def got_sleep_q(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["sleep_q"] = int(q.data.split(":")[1])
    await q.edit_message_text(
        "Были *сны*?",
        parse_mode="Markdown",
        reply_markup=yes_no_kb("dr:1", "dr:0", "Да 💭", "Нет 😶")
    )
    return DREAMS


async def got_dreams(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["dreams"] = int(q.data.split(":")[1])
    await q.edit_message_text(
        "Смотрел в *телефон* в первые 20 минут после пробуждения?",
        parse_mode="Markdown",
        reply_markup=yes_no_kb("ph:1", "ph:0", "Да 📱", "Нет 🙅")
    )
    return PHONE


async def got_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["phone_morning"] = int(q.data.split(":")[1])

    uid = get_uid(q.from_user.id)
    save_morning(uid, ctx.user_data)

    h = ctx.user_data["sleep_h"]
    sq = ctx.user_data["sleep_q"]
    ph = "📱 да" if ctx.user_data["phone_morning"] else "🙅 нет"

    await q.edit_message_text(
        f"✅ *Утро записано!*\n\n"
        f"😴 Сон: {h}ч  |  Качество: {sq}/5\n"
        f"📱 Телефон утром: {ph}\n\n"
        f"Хорошего дня! 💪",
        parse_mode="Markdown"
    )
    ctx.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменил.", reply_markup=main_kb())
    ctx.user_data.clear()
    return ConversationHandler.END


morning_conv = ConversationHandler(
    entry_points=[
        CommandHandler("morning", start),
        MessageHandler(filters.Regex("^🌅 Утренний опрос$"), start),
    ],
    states={
        SLEEP_H: [CallbackQueryHandler(got_sleep_h, pattern="^slh:")],
        SLEEP_Q: [CallbackQueryHandler(got_sleep_q, pattern="^slq:")],
        DREAMS:  [CallbackQueryHandler(got_dreams,  pattern="^dr:")],
        PHONE:   [CallbackQueryHandler(got_phone,   pattern="^ph:")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False,
)
