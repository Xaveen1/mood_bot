"""
ai_coach.py — AI-тренер.

Берёт данные из БД за неделю + прогресс ЕГЭ,
отправляет в Claude API, получает персональные советы
на основе методов стобалльников из файла "все про егэ".
"""

import httpx
import json
from telegram import Update
from telegram.ext import ContextTypes
from database import get_uid, get_week_stats, get_week_plan_stats, get_week_ege_stats, get_ege_settings
from keyboards import main_kb

EGE_KNOWLEDGE = """
Методы подготовки к ЕГЭ от стобалльников и топовых школ:

1. ДИСЦИПЛИНА > МОТИВАЦИЯ: Мотивация — кратковременный импульс. Дисциплина работает даже когда «не хочется».

2. СОН 8-9 ЧАСОВ: Недосып убивает концентрацию. Стобалльники спят полноценно — это не опция, а требование.

3. МЕТОД «ПЛАН МИНИМУМ — СРЕДНИЙ — МАКСИМУМ»:
   - Минимум: маленькая гарантированная задача даже в плохой день (1-2 часа)
   - Средний: обычная норма (4-5 часов)
   - Максимум: для дней с «куражом»
   Главное — не бросать совсем. Даже 10% лучше нуля.

4. ЦИКЛИЧЕСКОЕ ПОВТОРЕНИЕ: Возвращаться к темам через 1, 3, 7 дней. Идеи не «отваливаются» из памяти.

5. МЕТОД АКТИВНОГО ЗАПОМИНАНИЯ: Посмотрел → закрыл → воспроизвёл по памяти. Три раза.

6. ЗАДАЧИ ВЫШЕ УРОВНЯ ЕГЭ: После сложных задач реальный экзамен кажется простым.

7. СПОРТ ДАЁТ ЭНЕРГИЮ: 1-2 раза в неделю зал или прогулки. Спорт не забирает время — он его создаёт.

8. БОРЬБА С ТЕЛЕФОНОМ: Утренний телефон (первые 20 мин) разрушает концентрацию на весь день.

9. ФОКУС НА СЛАБЫХ МЕСТАХ: Не делать всё подряд «для галочки» — работать над тем, что проседает.

10. ВЫХОДНОЙ ДЕНЬ: Один полный выходной в неделю без учёбы — профилактика выгорания.
"""

SYSTEM_PROMPT = f"""Ты персональный AI-тренер для подготовки к ЕГЭ и личного развития.

У тебя есть данные о студенте за последнюю неделю: сон, настроение, энергия, привычки, задачи.

Твоя база знаний — методы реальных стобалльников:
{EGE_KNOWLEDGE}

Твоя задача:
1. Проанализировать данные
2. Найти конкретные паттерны (что коррелирует с высоким/низким настроением)
3. Дать 3-5 конкретных, персональных совета на следующую неделю
4. Мотивировать, но честно — не лесть, а реальная оценка

Стиль: дружелюбный, прямой, как хороший наставник. Без воды.
Формат: текст с эмодзи, абзацы. Не используй markdown заголовки с ##.
Длина: 250-400 слов. На русском языке."""


async def ai_coach_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update.effective_user.id)
    name = update.effective_user.first_name or "друг"

    await update.message.reply_text(
        "🤖 *AI-тренер думает...*\n\n_Анализирую твою неделю и готовлю персональные советы_",
        parse_mode="Markdown"
    )

    # Собираем данные
    week = get_week_stats(uid)
    plans = get_week_plan_stats(uid)
    ege_tasks = get_week_ege_stats(uid)
    ege_settings = get_ege_settings(uid)

    # Формируем контекст для AI
    data_summary = _build_data_summary(name, week, plans, ege_tasks, ege_settings)

    try:
        advice = await _call_claude(data_summary)
    except Exception as e:
        advice = _fallback_advice(week)

    await update.message.reply_text(
        f"🤖 *AI-тренер — персональный разбор*\n\n{advice}",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )


def _build_data_summary(name: str, week: dict, plans: dict,
                         ege_tasks: list, ege_settings: dict | None) -> str:
    lines = [f"Студент: {name}"]

    if week:
        sleep_fmt = week.get("avg_sleep_fmt", "нет данных")
        lines += [
            f"Данных за неделю: {week.get('days', 0)} из 7 дней",
            f"Среднее настроение: {week.get('avg_mood', '—')}/5",
            f"Средняя энергия: {week.get('avg_energy', '—')}/5",
            f"Средний сон: {sleep_fmt} (качество {week.get('avg_sleep_q', '—')}/5)",
            f"Спорт: {week.get('sport_pct', 0)}% дней",
            f"Медитация: {week.get('meditation_pct', 0)}% дней",
            f"Чтение: {week.get('reading_pct', 0)}% дней",
            f"Живое общение: {week.get('social_pct', 0)}% дней",
        ]
        if week.get("mood_by_dow"):
            lines.append("Настроение по дням: " +
                         ", ".join(f"{d}={v}" for d, v in week["mood_by_dow"].items()))
        if week.get("insights"):
            lines.append("Автоматические инсайты: " + "; ".join(week["insights"]))
    else:
        lines.append("Данных за неделю нет — пользователь только начал.")

    if plans:
        lines.append("\nВыполнение плана:")
        for subj, stat in plans.items():
            pct = round(stat["done"] / stat["planned"] * 100) if stat["planned"] else 0
            lines.append(f"  {subj}: {stat['done']}/{stat['planned']} ({pct}%)")

    if ege_tasks:
        lines.append("\nЗанятия ЕГЭ за неделю:")
        by_subj = {}
        for t in ege_tasks:
            s = t["subject"]
            by_subj.setdefault(s, {"total": 0, "done": 0, "types": []})
            by_subj[s]["total"] += 1
            by_subj[s]["done"] += t["done"]
            by_subj[s]["types"].append(t["task_type"])
        for s, stat in by_subj.items():
            types = ", ".join(set(stat["types"]))
            lines.append(f"  {s}: {stat['total']} занятий ({types})")

    if ege_settings:
        subjs = ", ".join(ege_settings.get("subjects", []))
        lines.append(f"\nПредметы ЕГЭ: {subjs}")

    return "\n".join(lines)


async def _call_claude(data: str) -> str:
    """Вызов Claude API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user",
                     "content": f"Вот данные студента за последнюю неделю:\n\n{data}\n\n"
                                f"Сделай анализ и дай конкретные советы на следующую неделю."}
                ]
            }
        )
        result = resp.json()
        return result["content"][0]["text"]


def _fallback_advice(week: dict) -> str:
    """Советы без AI если API недоступен — на основе данных."""
    tips = []

    if week:
        sleep_min = week.get("avg_sleep_min", 0) or 0
        if sleep_min < 420:
            tips.append("😴 *Сон критически важен.* У тебя меньше 7 часов. Стобалльники спят 8-9ч — это не роскошь, а топливо для мозга.")
        elif sleep_min >= 480:
            tips.append("✅ Со сном всё хорошо! Сохраняй этот режим.")

        sport = week.get("sport_pct", 0) or 0
        if sport < 30:
            tips.append("🏃 Добавь хотя бы 2 прогулки в неделю. Спорт создаёт энергию, а не тратит её.")

        mood = week.get("avg_mood", 3) or 3
        if mood < 3:
            tips.append("💪 Попробуй метод «план минимум»: ставь маленькую гарантированную цель на день. Выполнение даёт позитивное подкрепление.")

    if not tips:
        tips = [
            "📋 Заполняй дневник каждый день — чем больше данных, тем точнее советы.",
            "🔄 Используй циклическое повторение: возвращайся к пройденному через 1-3-7 дней.",
            "📵 Первые 20 минут после пробуждения — без телефона. Это меняет весь день.",
        ]

    return "\n\n".join(tips)
