from telegram import Update
from telegram.ext import ContextTypes
from database import (
    get_uid, get_week_stats, get_week_plan_stats,
    get_week_ege_stats, get_ege_settings
)
from keyboards import main_kb


def _bar(val: float, max_val: float = 5, w: int = 10) -> str:
    filled = round(val / max_val * w)
    return "█" * filled + "░" * (w - filled)


EGE_LABELS = {
    "russian":     "🇷🇺 Русский",
    "math":        "📐 Математика",
    "informatics": "💻 Информатика",
    "physics":     "⚛️ Физика",
    "chemistry":   "🧪 Химия",
    "biology":     "🌱 Биология",
    "history":     "📜 История",
    "social":      "🌍 Обществознание",
    "english":     "🇬🇧 Английский",
}

PLAN_LABELS = {
    "python":  "🐍 Python",
    "sport":   "🏃 Спорт",
    "reading": "📖 Чтение",
    "other":   "📌 Другое",
    "custom":  "📝 Свои задачи",
}


def build_report(user_id: int, name: str) -> str:
    s = get_week_stats(user_id)
    ps = get_week_plan_stats(user_id)
    ege_tasks = get_week_ege_stats(user_id)
    ege_settings = get_ege_settings(user_id)

    if not s and not ps and not ege_tasks:
        return (
            "📊 *Недельный отчёт*\n\n"
            "Данных пока нет — заполняй дневник каждый день!\n\n"
            "_Помни: даже план минимум лучше нуля_ 💪"
        )

    lines = [
        "╔═══════════════════════╗",
        "║  📊 ОТЧЁТ ЗА НЕДЕЛЮ   ║",
        "╚═══════════════════════╝",
        f"Привет, {name}!\n",
    ]

    # ── Самочувствие ──────────────────────────────────────
    if s:
        lines.append(f"*📈 Самочувствие* ({s['days']}/7 дней)\n")
        if s.get("avg_mood"):
            lines.append(f"Настроение  {_bar(s['avg_mood'])}  *{s['avg_mood']}/5*")
        if s.get("avg_energy"):
            lines.append(f"Энергия     {_bar(s['avg_energy'])}  *{s['avg_energy']}/5*")
        if s.get("avg_sleep_fmt"):
            q = s.get("avg_sleep_q", "—")
            # Подсказка по сну
            sleep_min = s.get("avg_sleep_min", 0) or 0
            sleep_warn = ""
            if sleep_min < 420:
                sleep_warn = " ⚠️ мало!"
            elif sleep_min >= 480:
                sleep_warn = " ✅"
            lines.append(f"Сон         {_bar(min(sleep_min/60, 5))}  *{s['avg_sleep_fmt']}*{sleep_warn} (кач. {q}/5)")
        lines.append("")

        # ── Настроение по дням ───────────────────────────
        if s.get("mood_by_dow"):
            lines.append("*📅 Настроение по дням*\n")
            emojis = {1:"😞",2:"😕",3:"😐",4:"🙂",5:"😄"}
            for dow in ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]:
                v = s["mood_by_dow"].get(dow)
                if v:
                    lines.append(f"{dow}  {_bar(v)}  {v} {emojis.get(v,'')}")
            lines.append("")

        # ── Привычки ─────────────────────────────────────
        lines.append("*✅ Привычки*\n")
        for key, lbl in [("sport_pct","🏃 Спорт"),("meditation_pct","🧘 Медитация"),
                          ("reading_pct","📚 Чтение"),("social_pct","👥 Общение вживую")]:
            v = s.get(key)
            if v is not None:
                lines.append(f"{lbl}  {_bar(v,100)}  *{v}%*")
        lines.append("")

    # ── ЕГЭ ───────────────────────────────────────────────
    if ege_tasks:
        lines.append("*📚 Занятия ЕГЭ*\n")
        by_subj: dict = {}
        type_names = {"new":"новые","repeat":"повтор","trial":"пробник","errors":"ошибки"}
        for t in ege_tasks:
            s_key = t["subject"]
            by_subj.setdefault(s_key, {"total":0,"done":0,"types":set(),"nums":[]})
            by_subj[s_key]["total"] += 1
            by_subj[s_key]["done"] += t.get("done", 0)
            by_subj[s_key]["types"].add(t["task_type"])
            if t.get("task_number"):
                by_subj[s_key]["nums"].append(t["task_number"])

        for s_key, stat in by_subj.items():
            lbl = EGE_LABELS.get(s_key, s_key)
            types_str = ", ".join(type_names.get(t,t) for t in stat["types"])
            pct = round(stat["done"]/stat["total"]*100) if stat["total"] else 0
            lines.append(f"{lbl}: *{stat['total']} занятий* ({types_str})")
            if stat["nums"]:
                nums_str = ", ".join(f"№{n}" for n in sorted(set(stat["nums"]))[:8])
                lines.append(f"  Задания: {nums_str}")
        lines.append("")

    # ── Задачи ───────────────────────────────────────────
    if ps:
        lines.append("*📋 Задачи*\n")
        for subj, stat in ps.items():
            lbl = PLAN_LABELS.get(subj, subj)
            planned = stat["planned"]
            done = stat["done"]
            pct = round(done/planned*100) if planned else 0
            fire = " 🔥" if pct == 100 else ""
            lines.append(f"{lbl}  {_bar(pct,100)}  *{done}/{planned}*{fire}")
        lines.append("")

    # ── Инсайты ──────────────────────────────────────────
    if s and s.get("insights"):
        lines.append("*💡 Что замечено*\n")
        for ins in s["insights"]:
            lines.append(f"▸ {ins}")
        lines.append("")

    # ── Совет недели ─────────────────────────────────────
    lines.append("*📖 Совет недели*")
    tips = [
        "Лучше сделать 10% от плана, чем ноль. Запусти себя — дальше пойдёт само.",
        "Циклическое повторение: вернись к темам, которые делал 3-7 дней назад.",
        "Спорт даёт энергию на учёбу, а не забирает её. Попробуй в этот раз.",
        "Первые 20 минут без телефона после пробуждения — и весь день другой.",
        "Найди одно задание ЕГЭ, которое даётся хуже всего, и проработай именно его.",
    ]
    # Выбираем совет по дням недели (чтобы менялся каждую неделю)
    from datetime import date
    tip_idx = date.today().isocalendar()[1] % len(tips)
    lines.append(f"_{tips[tip_idx]}_\n")

    lines.append("_Продолжай — каждый день важен! До следующего воскресенья 🔥_")
    return "\n".join(lines)


async def report_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update.effective_user.id)
    name = update.effective_user.first_name or "друг"
    text = build_report(uid, name)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_kb())


async def send_weekly_to_all(ctx: ContextTypes.DEFAULT_TYPE):
    import sqlite3
    from database import DB
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT tg_id, first_name FROM users")
        users = c.fetchall()

    for u in users:
        try:
            uid = get_uid(u["tg_id"])
            text = build_report(uid, u["first_name"] or "друг")
            await ctx.bot.send_message(u["tg_id"], text, parse_mode="Markdown")
        except Exception as e:
            print(f"[report] {u['tg_id']}: {e}")
