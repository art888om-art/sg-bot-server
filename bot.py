# -*- coding: utf-8 -*-
"""
CRM-бот для продавцов генераторов и стартеров.
Версия 2.0 – гривны, полноценное меню, зачатки CRM.
"""
import os, logging, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ConversationHandler, ContextTypes
)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
NOVA_POSHTA_API_KEY = os.getenv("NOVA_POSHTA_API_KEY", "")  # опционально

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Подключение к Google Таблице
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_key.json", scope)
client = gspread.authorize(creds)

# Основной лист с товарами (старый)
sheet = client.open_by_url(SHEET_URL).sheet1

# ---------- НОВЫЕ ЛИСТЫ (создаются автоматически при первом запуске) ----------
SHEET_STRUCTURE = {
    "Клиенты":   ["ID", "Имя", "Телефон", "Авто", "VIN", "Агрегат", "Тип", "Состояние", "Цена", "Комментарий", "Статус", "История"],
    "Агрегаты":  ["ID", "Тип", "Модель", "Аналог", "Характеристики", "Наличие", "Цена", "Гарантия"],
    "Сделки":    ["ID", "Клиент_ID", "Товар_ID", "Сумма", "Статус", "Дата"],
    "Звонки":    ["ID", "Менеджер", "Клиент_ID", "Результат", "Дата"],
    "Скрипты":   ["Возражение", "Ответ"],
    "Статистика":["Дата", "Продажи_кол", "Сумма", "Звонки_кол", "Конверсия"]
}

def init_sheets():
    """Создаёт новые листы с заголовками, если их ещё нет."""
    try:
        all_worksheets = client.open_by_url(SHEET_URL).worksheets()
        existing_titles = [ws.title for ws in all_worksheets]
        for name, headers in SHEET_STRUCTURE.items():
            if name not in existing_titles:
                ws = client.open_by_url(SHEET_URL).add_worksheet(title=name, rows="100", cols="20")
                ws.insert_row(headers, 1)
                logger.info(f"Лист '{name}' создан")
    except Exception as e:
        logger.error(f"Ошибка создания листов: {e}")

# Вызвать один раз при старте
init_sheets()

# ---------- КНОПКИ ----------
def main_keyboard():
    """Главное меню с новыми разделами."""
    buttons = [
        [KeyboardButton("📋 Клиенты"), KeyboardButton("🗄️ Агрегаты")],
        [KeyboardButton("📜 Скрипты"), KeyboardButton("📊 Аналитика")],
        [KeyboardButton("📈 Отчёт"), KeyboardButton("🔗 Поиск VIN/Агрегатов")],
        [KeyboardButton("🚚 Новая Почта"), KeyboardButton("🆘 Помощь")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def agregat_menu():
    """Подменю внутри '🗄️ Агрегаты' (старые функции)."""
    buttons = [
        [KeyboardButton("➕ Добавить товар")],
        [KeyboardButton("📋 Все товары"), KeyboardButton("🔍 Поиск по модели")],
        [KeyboardButton("✏️ Изменить статус"), KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (старые) ----------
STATUSES = ["в наличии", "продан", "в ремонте"]
(TYPE, MODEL, PRICE, STATUS, DESCRIPTION, PHOTO) = range(6)

def get_all_rows():
    """Возвращает все строки основного листа с товарами."""
    records = sheet.get_all_records()
    rows = []
    for idx, record in enumerate(records, start=2):
        record["_row"] = idx
        rows.append(record)
    return rows

async def check_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ---------- ОБРАБОТЧИКИ КОМАНД И КНОПОК ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать в CRM генераторов и стартеров!\nИспользуйте кнопки ниже.",
        reply_markup=main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 CRM бот\n\n"
        "📋 Клиенты — карточки клиентов (скоро)\n"
        "🗄️ Агрегаты — база товаров и добавление\n"
        "📜 Скрипты — готовые ответы на возражения\n"
        "📊 Аналитика — статистика (скоро)\n"
        "📈 Отчёт — ежедневный отчёт (скоро)\n"
        "🔗 Поиск VIN/Агрегатов — Avto.pro, Exist.ua\n"
        "🚚 Новая Почта — трекинг ТТН\n"
        "🆘 Помощь — это сообщение",
        reply_markup=main_keyboard()
    )

# --- Заглушки для новых разделов ---
async def clients_start(update, context):
    await update.message.reply_text(
        "📋 Раздел «Клиенты» пока в разработке.\n"
        "Здесь будет карточка клиента: имя, телефон, авто, VIN, агрегат, статус сделки и история.",
        reply_markup=main_keyboard()
    )

async def agregat_start(update, context):
    """Переход в подменю агрегатов."""
    await update.message.reply_text("🗄️ База агрегатов — выберите действие:", reply_markup=agregat_menu())

async def scripts_start(update, context):
    """Показывает готовые ответы на возражения."""
    text = (
        "📜 *Скрипты продаж*\n\n"
        "• *Дорого*: «Мы даём гарантию 12 мес, цена оправдана.»\n"
        "• *Хочу по месту*: «Отправляем Новой Почтой за 1-2 дня, оплата при получении.»\n"
        "• *Не доверяю отправке*: «Работаем более 5 лет, множество отзывов.»\n"
        "• *Подумаю*: «Товар в дефиците, лучше забронировать сейчас.»\n"
        "• *Если не подойдёт?*: «Пришлём фото и VIN-сверку, возврат в течение 14 дней.»\n"
        "• *Есть ли гарантия?*: «Да, 12 месяцев официальной гарантии.»\n"
        "• *Я ещё посмотрю*: «Пришлите VIN, я проверю наличие аналогов.»\n"
        "• *Скиньте фото*: «Фото высылаем в чат, также можете запросить видео.»\n"
        "• *А это точно подойдёт?*: «Сверяем по VIN и маркировке, даём 100% гарантию совместимости.»"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def analytics_start(update, context):
    await update.message.reply_text(
        "📊 Аналитика появится после накопления данных.\n"
        "Будут отображаться конверсия, эффективность менеджеров, популярные товары.",
        reply_markup=main_keyboard()
    )

async def report_start(update, context):
    await update.message.reply_text(
        "📈 Ежедневный отчёт будет автоматически отправляться админам в конце дня (скоро).",
        reply_markup=main_keyboard()
    )

async def search_start(update, context):
    """Кнопки-ссылки на Avto.pro и Exist.ua."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚗 Avto.pro (подбор агрегатов)", url="https://avto.pro/catalog/")],
        [InlineKeyboardButton("🔎 Exist.ua (пробив по VIN)", url="https://exist.ua/")],
    ])
    await update.message.reply_text(
        "🔗 Выберите сервис для поиска:",
        reply_markup=keyboard
    )

async def nova_poshta_start(update, context):
    """Кнопка-ссылка на отслеживание Новой Почты."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Перейти на сайт Новой Почты", url="https://tracking.novaposhta.ua/")],
    ])
    await update.message.reply_text(
        "🚚 *Новая Почта*\n"
        "Для отслеживания посылки перейдите по ссылке и введите номер ТТН.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# --- Обработка главного меню ---
async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📋 Клиенты":
        await clients_start(update, context)
    elif text == "🗄️ Агрегаты":
        await agregat_start(update, context)
    elif text == "📜 Скрипты":
        await scripts_start(update, context)
    elif text == "📊 Аналитика":
        await analytics_start(update, context)
    elif text == "📈 Отчёт":
        await report_start(update, context)
    elif text == "🔗 Поиск VIN/Агрегатов":
        await search_start(update, context)
    elif text == "🚚 Новая Почта":
        await nova_poshta_start(update, context)
    elif text == "🆘 Помощь":
        await help_command(update, context)
    elif text == "🔙 Назад":
        await update.message.reply_text("Главное меню:", reply_markup=main_keyboard())
    else:
        # Если пришла кнопка из агрегатного подменю – обработаем отдельно
        await old_functions(update, context)

# --- Перенаправление старых кнопок (когда находимся в подменю агрегатов) ---
async def old_functions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📋 Все товары":
        await show_all_products(update, context)
    elif text == "✏️ Изменить статус":
        await change_status_start(update, context)
    elif text == "➕ Добавить товар":
        # Запустить старый диалог добавления
        await update.message.reply_text(
            "Выберите тип товара:",
            reply_markup=ReplyKeyboardMarkup([["Генератор", "Стартер"]], one_time_keyboard=True, resize_keyboard=True)
        )
        return TYPE
    elif text == "🔍 Поиск по модели":
        await update.message.reply_text("Введите модель для поиска:")
        return 0  # состояние поиска
    elif text == "🔙 Назад":
        await update.message.reply_text("Главное меню:", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("Используйте кнопки меню.")

# ---------- СТАРЫЕ ФУНКЦИИ (с заменой рублей на гривны) ----------
async def show_all_products(update, context):
    rows = get_all_rows()
    if not rows:
        await update.message.reply_text("📭 Товаров пока нет.")
        return
    keyboard = []
    for row in rows[:10]:
        label = f"{row['Модель']} ({row['Статус']}) - {row['Цена']}₴"  # <-- гривна
        keyboard.append([InlineKeyboardButton(label, callback_data=f"detail_{row['_row']}")])
    reply = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 Все товары:", reply_markup=reply)

async def product_detail(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "show_more":
        await query.edit_message_text("Функция листания пока не реализована.")
        return
    row_num = int(data.split("_")[1])
    try:
        row_values = sheet.row_values(row_num)
        if len(row_values) < 7:
            await query.edit_message_text("Ошибка: неполные данные.")
            return
        _, typ, model, price, status, desc, photo_id = row_values[:7]
        text = (
            f"*{typ}* — {model}\n"
            f"Цена: {price}₴\n"
            f"Статус: {status}\n"
            f"Описание: {desc}"
        )
        if photo_id:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo_id,
                caption=text,
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка деталей: {e}")
        await query.edit_message_text("Не удалось загрузить данные.")

# --- Добавление товара (Conversation) ---
async def add_product_start(update, context):
    await update.message.reply_text(
        "Выберите тип товара:",
        reply_markup=ReplyKeyboardMarkup([["Генератор", "Стартер"]], one_time_keyboard=True, resize_keyboard=True)
    )
    return TYPE

async def add_type(update, context):
    text = update.message.text
    if text not in ["Генератор", "Стартер"]:
        await update.message.reply_text("Пожалуйста, выберите Генератор или Стартер.")
        return TYPE
    context.user_data["type"] = text
    await update.message.reply_text("Введите модель:", reply_markup=agregat_menu())
    return MODEL

async def add_model(update, context):
    model = update.message.text.strip()
    if not model:
        await update.message.reply_text("Модель не может быть пустой.")
        return MODEL
    context.user_data["model"] = model
    await update.message.reply_text("Введите цену (число, в гривнах):")
    return PRICE

async def add_price(update, context):
    try:
        price = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Цена должна быть целым числом.")
        return PRICE
    context.user_data["price"] = price
    await update.message.reply_text(
        "Выберите статус:",
        reply_markup=ReplyKeyboardMarkup([[s] for s in STATUSES], one_time_keyboard=True, resize_keyboard=True)
    )
    return STATUS

async def add_status(update, context):
    status = update.message.text.strip()
    if status not in STATUSES:
        await update.message.reply_text("Выберите статус из предложенных.")
        return STATUS
    context.user_data["status"] = status
    await update.message.reply_text("Введите описание (или 'нет'):", reply_markup=agregat_menu())
    return DESCRIPTION

async def add_description(update, context):
    desc = update.message.text.strip()
    if desc.lower() in ["нет", "-", "нету", "no"]:
        desc = ""
    context.user_data["description"] = desc
    await update.message.reply_text("Отправьте фото товара (или напишите 'нет'):")
    return PHOTO

async def add_photo(update, context):
    photo_id = ""
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    elif update.message.text and update.message.text.strip().lower() in ["нет", "no", "-"]:
        pass
    else:
        await update.message.reply_text("Отправьте фото или напишите 'нет'.")
        return PHOTO

    data = context.user_data
    all_rows = get_all_rows()
    new_id = max([int(r["ID"]) for r in all_rows if r["ID"].isdigit()] + [0]) + 1
    try:
        sheet.append_row([
            str(new_id), data["type"], data["model"], str(data["price"]),
            data["status"], data["description"], photo_id
        ])
        await update.message.reply_text(
            f"✅ Товар *{data['model']}* добавлен! (ID {new_id})",
            parse_mode="Markdown", reply_markup=agregat_menu()
        )
    except Exception as e:
        logger.error(f"Ошибка записи: {e}")
        await update.message.reply_text("❌ Не удалось сохранить товар.", reply_markup=agregat_menu())
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_add(update, context):
    await update.message.reply_text("Добавление отменено.", reply_markup=agregat_menu())
    context.user_data.clear()
    return ConversationHandler.END

# --- Изменение статуса ---
async def change_status_start(update, context):
    rows = get_all_rows()
    if not rows:
        await update.message.reply_text("Нет товаров.")
        return
    keyboard = []
    for row in rows:
        label = f"{row['Модель']} ({row['Статус']})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"status_{row['_row']}")])
    await update.message.reply_text("Выберите товар:", reply_markup=InlineKeyboardMarkup(keyboard))

async def status_select_product(update, context):
    query = update.callback_query
    await query.answer()
    row_num = int(query.data.split("_")[1])
    context.user_data["edit_row"] = row_num
    keyboard = [[InlineKeyboardButton(s, callback_data=f"setstatus_{s}")] for s in STATUSES]
    await query.edit_message_text("Новый статус:", reply_markup=InlineKeyboardMarkup(keyboard))

async def status_set_new(update, context):
    query = update.callback_query
    await query.answer()
    new_status = query.data.split("_")[1]
    row_num = context.user_data.get("edit_row")
    if not row_num:
        await query.edit_message_text("Ошибка сессии.")
        return
    try:
        sheet.update_cell(row_num, 5, new_status)
        await query.edit_message_text(f"✅ Статус изменён на *{new_status}*", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка обновления статуса: {e}")
        await query.edit_message_text("❌ Не удалось обновить статус.")
    finally:
        context.user_data.pop("edit_row", None)

# --- Поиск ---
async def search_model_input(update, context):
    query = update.message.text.strip()
    rows = get_all_rows()
    results = [r for r in rows if query.lower() in r["Модель"].lower()]
    if not results:
        await update.message.reply_text("🔍 Ничего не найдено.", reply_markup=agregat_menu())
        return ConversationHandler.END
    keyboard = []
    for r in results[:5]:
        label = f"{r['Модель']} ({r['Статус']}) - {r['Цена']}₴"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"detail_{r['_row']}")])
    await update.message.reply_text("🔍 Результаты поиска:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# ---------- HTTP СЕРВЕР ДЛЯ RENDER ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Запуск HTTP-сервера (чтобы Render не убивал сервис и для будущих отчётов)
    port = int(os.environ.get("PORT", 8000))
    web_dir = os.path.join(os.path.dirname(__file__), "templates")
    os.chdir(web_dir)
    def run_http_server():
        HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler).serve_forever()
    threading.Thread(target=run_http_server, daemon=True).start()
    logger.info(f"HTTP сервер запущен на порту {port}")

    # --- ConversationHandler для добавления товара ---
    add_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Добавить товар$"), add_product_start)],
        states={
            TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_type)],
            MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_model)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price)],
            STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_status)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_description)],
            PHOTO: [
                MessageHandler(filters.PHOTO, add_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_photo),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_add)],
    )

    # ConversationHandler для поиска
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Поиск по модели$"), lambda u, c: search_model_input(u, c))],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_model_input)],
        },
        fallbacks=[],
    )

    app.add_handler(add_conv)
    app.add_handler(search_conv)

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export", lambda u, c: u.message.reply_text(SHEET_URL)))

    # Callback-обработчики
    app.add_handler(CallbackQueryHandler(product_detail, pattern="^detail_"))
    app.add_handler(CallbackQueryHandler(status_select_product, pattern="^status_"))
    app.add_handler(CallbackQueryHandler(status_set_new, pattern="^setstatus_"))

    # Текстовые сообщения (кнопки меню)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))

    # Запуск бота
    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
