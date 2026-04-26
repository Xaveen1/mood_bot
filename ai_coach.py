"""
ai_coach.py — AI-тренер.

Берёт данные из БД за неделю + прогресс ЕГЭ,
отправляет в Claude API, получает персональные советы
на основе методов стобалльников + методик обучения программированию.
"""

import os
import httpx
import json
from telegram import Update
from telegram.ext import ContextTypes
from database import get_uid, get_week_stats, get_week_plan_stats, get_week_ege_stats, get_ege_settings
from keyboards import main_kb

STUDENT_KNOWLEDGE = """
МЕТОДЫ ОБУЧЕНИЯ ПРОГРАММИРОВАНИЮ (доказанные):

1. ПРИНЦИП 90/10: 90-95% времени — в редакторе кода, что-то запускать и ломать.
   Только 5-10% — лекции и книги. Главная ошибка новичков — пассивный просмотр курсов.

2. AI КАК МЕНТОР (ChatGPT/Claude): Просить делать code review твоего кода,
   объяснять ошибки, разбирать концепции на примерах. AI заменяет ментора на 99%.
   Правильный запрос: "Вот мой код — найди ошибки, объясни что можно улучшить".

3. REMNOTE КАРТОЧКИ — когда и как использовать:
   - КОГДА создавать: сразу после того как понял новую концепцию (синтаксис, паттерн, алгоритм).
     Не во время обучения, а после — когда закрыл урок.
   - КОГДА повторять: каждый день по 10-15 минут ПЕРЕД новой учёбой (интервальное повторение).
   - ЧТО вносить: не определения из интернета, а своими словами + пример кода.
   - Примеры хороших карточек: "Что делает list comprehension?" → [x for x in lst if x > 0]

4. NOTION ДЛЯ СТУДЕНТА:
   - База знаний: конспекты по темам, ссылки на ресурсы.
   - Трекер проектов: статус, следующий шаг, дедлайн.
   - Ошибки и решения: записывать баги которые долго искал — потом экономит часы.
   - Дорожная карта: что изучил, что следующее.

5. УРОВНИ РАЗВИТИЯ ПРОГРАММИСТА:
   - Уровень 1: Простые задачи на логику (Codewars, LeetCode Easy).
   - Уровень 2: Консольные программы и мини-игры (Змейка, калькулятор, угадай число).
   - Уровень 3: Реальный сервис для людей (Telegram-бот, сайт, API).

6. АКТИВНОЕ ВОСПРОИЗВЕДЕНИЕ: Посмотрел урок → закрыл → написал код по памяти.
   Через 20 минут не подглядывая. Это лучше чем просмотреть 5 уроков подряд.

7. АНГЛИЙСКИЙ — навык "тир-1.5": документация, Stack Overflow, GitHub Issues —
   всё на английском. Начни читать хотя бы по 15 минут документации в день.

АНТИВЫГОРАНИЕ И ПСИХОЛОГИЯ СТУДЕНТА-ПРОГРАММИСТА:

1. ПЛАН МИНИМУМ / СРЕДНИЙ / МАКСИМУМ:
   - Минимум: хотя бы 30 минут кода даже в самый плохой день. Не ноль.
   - Средний: обычная норма 2-4 часа.
   - Максимум: когда есть кураж. Не перегореть!

2. ПОМОДОРО ДЛЯ ПРОГРАММИСТОВ: 25 минут фокуса → 5 минут отдыха.
   После 4 помодоро — 20-30 минут полного отдыха (не телефон).

3. ВЫХОДНОЙ ОБЯЗАТЕЛЕН: Один полный день без кода и учёбы в неделю.
   Это не слабость — это профилактика выгорания.

4. СОН 7-9 ЧАСОВ: Мозг консолидирует код во сне. Недосып → ошибки → фрустрация → бросить.

5. СПОРТ = ЭНЕРГИЯ ДЛЯ КОДА: 2-3 раза в неделю. После тренировки концентрация выше.

6. ПРИНЦИП "МАЛЕНЬКИХ ПОБЕД": Каждый день должна быть хоть одна маленькая победа в коде.
   Не "выучить Python", а "написать функцию которая работает".

7. СРАВНИВАЙ ТОЛЬКО С СОБОЙ ВЧЕРА: Прогресс в программировании нелинейный.
   Неделями ничего, потом резкий скачок. Это нормально.
"""

SYSTEM_PROMPT = f"""Ты персональный AI-тренер для студента-программиста.

У тебя есть данные о студенте за последнюю неделю: сон, настроение, энергия, привычки, задачи по программированию, ЕГЭ.

Твоя база знаний — доказанные методы обучения и антивыгорания:
{STUDENT_KNOWLEDGE}

Твоя задача:
1. Проанализировать данные — найти конкретные паттерны
2. Дать 3-5 конкретных персональных советов на следующую неделю
3. Если мало данных по программированию — мотивировать начать с малого
4. Прокомментировать баланс: учёба / спорт / отдых / сон
5. Напомнить про RemNote если человек мало практиковался с карточками

Стиль: дружелюбный, прямой, как хороший наставник-разработчик. Без воды и лести.
Честная оценка + конкретные шаги. Уважай что студент совмещает учёбу, код и жизнь.
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
        advice = _fallback_advice(week, plans)

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
        lines.append("\nВыполнение плана по направлениям:")
        label_map = {
            "coding": "Программирование", "remnote": "RemNote карточки",
            "notion": "Notion", "sport": "Спорт", "reading": "Чтение",
            "english": "Английский", "other": "Другое", "custom": "Свои задачи",
        }
        for subj, stat in plans.items():
            pct = round(stat["done"] / stat["planned"] * 100) if stat["planned"] else 0
            lbl = label_map.get(subj, subj)
            lines.append(f"  {lbl}: {stat['done']}/{stat['planned']} ({pct}%)")

        # Отдельно проверяем RemNote и Notion
        remnote_stat = plans.get("remnote", {})
        if not remnote_stat:
            lines.append("  ⚠️ RemNote карточки не планировались на этой неделе")
        notion_stat = plans.get("notion", {})
        if not notion_stat:
            lines.append("  ⚠️ Notion не использовался на этой неделе")
    else:
        lines.append("\nПлан на неделю не заполнялся.")

    if ege_tasks:
        lines.append("\nЗанятия ЕГЭ за неделю:")
        by_subj: dict = {}
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
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
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
        if "error" in result:
            raise Exception(result["error"].get("message", "API error"))
        return result["content"][0]["text"]


def _fallback_advice(week: dict, plans: dict) -> str:
    """Советы без AI если API недоступен — на основе данных."""
    tips = []

    if week:
        sleep_min = week.get("avg_sleep_min", 0) or 0
        if sleep_min < 420:
            tips.append("😴 *Сон — приоритет №1.* У тебя меньше 7 часов. Мозг консолидирует код во сне — недосып это не экономия времени, а его трата.")
        elif sleep_min >= 480:
            tips.append("✅ Со сном всё хорошо — это фундамент всего остального!")

        sport = week.get("sport_pct", 0) or 0
        if sport < 30:
            tips.append("🏃 Добавь хотя бы 2 прогулки в неделю. После физической активности концентрация на коде заметно выше.")

        mood = week.get("avg_mood", 3) or 3
        if mood < 3:
            tips.append("💪 *Метод «план минимум»:* ставь маленькую цель — написать одну функцию, решить одну задачу. Маленькие победы строят импульс.")

    # Проверяем RemNote
    if not plans.get("remnote"):
        tips.append("🃏 *RemNote карточки:* попробуй сегодня создать 3-5 карточек по последней теме. Повторяй утром перед новой учёбой — это мощнее чем перечитывать конспекты.")

    # Проверяем программирование
    coding_stat = plans.get("coding", {})
    if not coding_stat or coding_stat.get("planned", 0) == 0:
        tips.append("💻 *Принцип 90/10:* 90% времени должно быть в редакторе. Попробуй сегодня не смотреть урок, а сразу писать код — это ускоряет обучение в разы.")

    if not tips:
        tips = [
            "📋 Заполняй дневник каждый день — чем больше данных, тем точнее советы AI.",
            "🃏 *RemNote:* создавай карточки сразу после урока, повторяй 10 минут каждое утро.",
            "💻 *Правило:* каждый день хоть 30 минут кода. Даже в плохой день — не ноль.",
        ]

    return "\n\n".join(tips)
