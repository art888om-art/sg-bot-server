"""All user-visible bot strings in one place. Easy to translate later."""

from __future__ import annotations

START = (
    "👋 Привет, <b>{name}</b>!\n\n"
    "Это AutoCRM — управление продажами генераторов и стартеров.\n"
    "Выбери раздел в меню ниже."
)
ACCESS_DENIED = "🚫 Доступ запрещён. Обратитесь к администратору."
GENERIC_ERROR = "⚠️ Что-то пошло не так. Я уже передал ошибку администратору."

LOGIN_CODE = (
    "🔐 <b>Код для входа в веб-CRM</b>\n\n"
    "<code>{code}</code>\n\n"
    "Действует 5 минут. Введи его на странице <a href='{url}'>{url}</a>."
)

HELP = (
    "ℹ️ <b>Команды AutoCRM</b>\n\n"
    "/start — главное меню\n"
    "/login — получить код для входа в веб\n"
    "/clients — мои клиенты\n"
    "/products — товары на складе\n"
    "/analytics — мои показатели\n"
    "/cancel — отменить текущую операцию"
)

CANCELLED = "❌ Отменено."

# Client FSM
CLIENT_ASK_NAME = "👤 Введи <b>имя</b> клиента:"
CLIENT_ASK_PHONE = "📞 Введи <b>телефон</b> (например, +380501234567):"
CLIENT_ASK_AUTO = (
    "🚗 Какая у клиента машина? (марка/модель/год)\nИли отправь «-», чтобы пропустить."
)
CLIENT_ASK_COMMENT = "💬 Добавь комментарий или отправь «-»:"
CLIENT_INVALID_PHONE = "Не похоже на номер. Попробуй ещё раз, например <code>+380501234567</code>."
CLIENT_SAVED = "✅ Клиент <b>{name}</b> сохранён (ID {id})."

# Buttons
BTN_CLIENTS = "📋 Клиенты"
BTN_PRODUCTS = "🗄️ Товары"
BTN_DEALS = "💰 Сделки"
BTN_TASKS = "📝 Задачи"
BTN_ANALYTICS = "📊 Аналитика"
BTN_SEARCH = "🔍 Поиск"
BTN_HELP = "🆘 Помощь"
BTN_ADD = "➕ Добавить"
BTN_CANCEL = "❌ Отмена"
BTN_BACK = "⬅️ Назад"
