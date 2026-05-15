# AutoCRM — Telegram-бот + веб-CRM для продажи генераторов и стартеров

Лёгкая B2B/B2C CRM на Google Sheets: Telegram-бот (aiogram 3) + веб-кабинет (FastAPI + Jinja2). Полная спецификация — в [`autocrm-prompt.md`](./autocrm-prompt.md).

## Стек
- Python 3.12 · aiogram 3 · FastAPI · Pydantic v2
- Google Sheets (gspread) с TTL-кэшем + retry/backoff + асинхронным lock
- JWT-cookie auth · CSRF (double-submit) · slowapi rate-limit
- structlog (JSON в проде, console в дев)
- pytest · ruff · mypy · pre-commit · GitHub Actions CI
- Docker · Render.com (`render.yaml`)

## Локальный запуск
```bash
cp .env.example .env           # отредактируй BOT_TOKEN, GOOGLE_SHEET_URL и т.д.
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install              # хуки для качества
pytest                          # тесты (≥60% coverage)
uvicorn app.main:app --reload   # веб на http://localhost:8000
```

Бот запускается тем же процессом — режим выбирается через `BOT_MODE`:
- `polling` (по умолчанию для dev) — стандартный long-poll;
- `webhook` — `WEBHOOK_BASE_URL` + `WEBHOOK_SECRET` обязательны.

## Структура
```
app/
├── bot/            # aiogram-роутеры, FSM, клавиатуры, middlewares
├── web/            # FastAPI приложение + Jinja2 шаблоны + REST API
├── domain/         # Pydantic-модели (Client, Product, Deal, Task, Manager)
├── repositories/   # обёртки над Google Sheets (по одному репо на сущность)
├── services/       # бизнес-логика + RBAC
└── integrations/   # SheetsClient (async + cache + retry), Nova Poshta
tests/              # unit + integration (pytest + httpx)
.github/workflows/  # CI (lint → types → tests → coverage)
```

## Переменные окружения
Полный список — в `.env.example`. Ключевые:
- `BOT_TOKEN` — токен Telegram-бота (`@BotFather`).
- `GOOGLE_SHEET_URL` — ссылка на таблицу.
- `GOOGLE_CREDENTIALS_FILE` — путь к service-account JSON (Editor права на таблицу).
- `JWT_SECRET` — ≥32 байта (в dev можно любой, в production генерируется Render-ом).
- `OWNER_IDS` — Telegram-ID владельцев через запятую (авторегистрация при старте).
- `BOT_MODE=webhook` + `WEBHOOK_BASE_URL` + `WEBHOOK_SECRET` — для прода на Render.

## Деплой на Render
1. Залогинься в Render → New Blueprint → выбери репозиторий — он подхватит `render.yaml`.
2. В Secret Files добавь `/etc/secrets/google_key.json` (service-account).
3. В Environment пропиши: `BOT_TOKEN`, `GOOGLE_SHEET_URL`, `OWNER_IDS`, `WEBHOOK_BASE_URL` (например `https://crm-bot.onrender.com`), `WEBHOOK_SECRET`.
4. После деплоя бот сам зарегистрирует webhook на `${WEBHOOK_BASE_URL}/tg/webhook`.

## Команды качества
```bash
ruff format app tests       # форматирование
ruff check app tests        # линт
mypy app                    # типы
pytest --cov=app            # тесты + покрытие
pre-commit run --all-files  # всё разом
```

## Безопасность
Реализовано (см. §10 спецификации):
- Все секреты — только в env (никаких хардкодов).
- JWT cookie — HttpOnly + Secure + SameSite=Lax.
- CSRF double-submit на всех мутирующих запросах.
- Rate-limit на `/login` и `/api/*` (slowapi).
- Защита от формула-инъекций в Google Sheets (`safe_cell`).
- Webhook secret на `/tg/webhook`.
- Никакого логирования токенов и личных данных.

## Лицензия
Внутренний проект.
