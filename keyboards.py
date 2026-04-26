from telegram import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        ["🌅 Утренний опрос",  "🌙 Вечерний дневник"],
        ["📚 ЕГЭ",             "📋 План на день"],
        ["✅ Отметить",         "📊 Мой день"],
        ["📈 Отчёт недели",    "🤖 AI-тренер"],
    ], resize_keyboard=True, one_time_keyboard=False)


def ikb(rows: list[list[tuple]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t, callback_data=d) for t, d in row]
        for row in rows
    ])


def score_kb(prefix: str) -> InlineKeyboardMarkup:
    return ikb([[(str(i), f"{prefix}:{i}") for i in range(1, 6)]])


def yes_no_kb(yes_data: str, no_data: str,
              yes_label="Да ✅", no_label="Нет ❌") -> InlineKeyboardMarkup:
    return ikb([[(yes_label, yes_data), (no_label, no_data)]])
