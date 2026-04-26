from telegram import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)


# ══════════════════════════════════════════
# ГЛАВНОЕ МЕНЮ (постоянные кнопки внизу)
# ══════════════════════════════════════════

def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        ["🌅 Утренний опрос",  "🌙 Вечерний дневник"],
        ["📋 План на день",    "✅ Отметить выполнено"],
        ["📊 Мой день",        "📈 Отчёт за неделю"],
    ], resize_keyboard=True, one_time_keyboard=False)


# ══════════════════════════════════════════
# INLINE — вспомогалки
# ══════════════════════════════════════════

def ikb(rows: list[list[tuple]]) -> InlineKeyboardMarkup:
    """ikb([[('Текст', 'data'), ...], ...])"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t, callback_data=d) for t, d in row]
        for row in rows
    ])


def score_kb(prefix: str) -> InlineKeyboardMarkup:
    """Кнопки 1–5 с префиксом."""
    return ikb([[(str(i), f"{prefix}:{i}") for i in range(1, 6)]])


def yes_no_kb(yes_data: str, no_data: str,
              yes_label="Да ✅", no_label="Нет ❌") -> InlineKeyboardMarkup:
    return ikb([[(yes_label, yes_data), (no_label, no_data)]])
