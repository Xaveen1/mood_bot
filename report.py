from telegram import Update
from telegram.ext import ContextTypes
from database import get_uid, get_week_stats, get_week_plan_stats, all_tg_ids
from keyboards import main_kb


def _bar(val: float, max_val: float = 5, w: int = 10) -> str:
    filled = round(val / max_val * w)
    return "█" * filled + "░" * (w - filled)


def build_report(user_id: int, name: str) -> str:
    s = get_week_stats(user_id)
    ps = get_week_plan_stats(user_id)

    if not s and not ps:
        return (
            "📊 *Недельный отчёт*\n\n"
            "Данных пока нет — заполняй дневник каждый день "
            "и в следующее воскресенье будет полный отчёт! 💪"
        )

    lines = [
        f"╔══════════════════════╗",
        f"║  📊 ОТЧЁТ ЗА НЕДЕЛЮ  ║",
        f"╚══════════════════════╝",
        f"Привет, {name}! Вот твоя неделя:\n",
    ]

    # ── Ключевые метрики ─────────────────────────────────
    if s:
        lines.append(f"*📈 Самочувствие* ({s['days']}/7 дней)\n")
        if s.get("avg_mood"):
            lines.append(f"Настроение  {_bar(s['avg_mood'])}  *{s['avg_mood']}/5*")
        if s.get("avg_energy"):
            lines.append(f"Энергия     {_bar(s['avg_energy'])}  *{s['avg_energy']}/5*")
        if s.get("avg_sleep_h"):
            lines.append(
                f"Сон         {_bar(s['avg_sleep_h'], 9)}  "
                f"*{s['avg_sleep_h']}ч* (кач. {s.get('avg_sleep_q','—')}/5)"
            )
        lines.append("")

        # ── Настроение по дням ───────────────────────────
        if s.get("mood_by_dow"):
            lines.append("*📅 Настроение по дням*\n")
            for dow in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
                v = s["mood_by_dow"].get(dow)
                if v:
                    emoji = ["", "😞", "😕", "😐", "🙂", "😄"][v]
                    lines.append(f"{dow}  {_bar(v)}  {v} {emoji}")
            lines.append("")

        # ── Привычки ─────────────────────────────────────
        lines.append("*✅ Привычки*\n")
        habits = [
            ("sport_pct",      "🏃 Спорт"),
            ("meditation_pct", "🧘 Медитация"),
            ("reading_pct",    "📚 Чтение"),
            ("social_pct",     "👥 Общение"),
        ]
        for key, lbl in habits:
            v = s.get(key)
            if v is not None:
                lines.append(f"{lbl}  {_bar(v, 100)}  *{v}%*")
        lines.append("")

    # ── Задачи ───────────────────────────────────────────
    if ps:
        LABELS = {
            "ege":     "📚 ЕГЭ",
            "python":  "🐍 Python",
            "sport":   "🏃 Спорт",
            "reading": "📖 Чтение",
        }
        lines.append("*📋 Задачи*\n")
        for subj, stat in ps.items():
            lbl = LABELS.get(subj, subj)
            planned = stat["planned"]
            done = stat["done"]
            pct = round(done / planned * 100) if planned else 0
            lines.append(f"{lbl}  {_bar(pct, 100)}  *{done}/{planned}*")
        lines.append("")

    # ── Инсайты ──────────────────────────────────────────
    if s and s.get("insights"):
        lines.append("*💡 Инсайты*\n")
        for ins in s["insights"]:
            lines.append(f"▸ {ins}")
        lines.append("")

    lines.append("_Продолжай — ты молодец! До следующего воскресенья 🔥_")
    return "\n".join(lines)


async def report_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update.effective_user.id)
    name = update.effective_user.first_name or "друг"
    text = build_report(uid, name)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_kb())


async def send_weekly_to_all(ctx: ContextTypes.DEFAULT_TYPE):
    """Вызывается планировщиком каждое воскресенье."""
    import sqlite3
    from database import DB
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT tg_id, first_name FROM users")
        users = c.fetchall()

    for u in users:
        try:
            uid_row = get_uid(u["tg_id"])
            text = build_report(uid_row, u["first_name"] or "друг")
            await ctx.bot.send_message(u["tg_id"], text, parse_mode="Markdown")
        except Exception as e:
            print(f"[report] ошибка для {u['tg_id']}: {e}")
