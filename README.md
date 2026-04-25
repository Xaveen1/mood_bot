# 📔 Дневник самочувствия — Telegram Bot

## Что умеет

| Команда | Что делает |
|---|---|
| `/morning` | Утренний опрос: сон (часы + качество), сны, телефон |
| `/evening` | Вечерний: настроение, энергия, спорт, вода, привычки, заметка |
| `/stats` | Недельный отчёт вручную в любой момент |
| `/notify` | Настроить время напоминаний |

**Автоматически:**
- 07:30 → напоминание утреннего опроса
- 22:00 → напоминание вечернего дневника
- 13:00 / 14:00 / 15:00 → дневные напоминания
- Воскресенье 20:00 → недельный отчёт


## Структура файлов

```
diary_bot/
├── bot.py          # точка входа, планировщик
├── handlers.py     # все диалоги (утро, вечер, уведомления)
├── database.py     # SQLite: таблицы, сохранение, статистика
├── requirements.txt
├── .env            # TOKEN=... (создай сам, не коммить в git!)
└── .env.example
```


## Локальный запуск

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Создать .env
cp .env.example .env
# Открой .env и вставь токен от @BotFather

# 3. Запустить
python bot.py
```


## Деплой на Railway (бесплатно 24/7)

1. Зарегистрируйся на [railway.app](https://railway.app)
2. New Project → Deploy from GitHub (запушь код на GitHub)
3. Или: New Project → Deploy from local → загрузи папку
4. В настройках проекта → Variables → добавь: `TOKEN = твой_токен`
5. Добавь файл `Procfile` в корень:
   ```
   worker: python bot.py
   ```
6. Deploy → бот работает 24/7 ✅

**Альтернатива — Render.com:**
1. New Web Service → тип: Worker
2. Build Command: `pip install -r requirements.txt`
3. Start Command: `python bot.py`
4. Environment: добавь TOKEN


## Как доделать (TODO для тебя)

Код специально написан с запасом — места для роста:

```python
# database.py → save_entry() — добавь новые поля прямо в dict
# handlers.py → вечерний опрос — добавь шаги между E_SOCIAL и E_NOTE
# handlers.py → notify_conv — добавь выбор дней недели (N_DAYS шаг)
# bot.py → job_random_reminder — читай настройки юзера из БД (get_notification_settings)
```

Данные уже все есть в БД — просто подключи логику.
