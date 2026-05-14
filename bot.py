# -*- coding: utf-8 -*-
"""
CRM-бот для продавцов генераторов и стартеров.
Хранит данные в Google Таблице, фото — через Telegram (file_id).
"""
import os
import logging
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler, ContextTypes

# Загружаем секретные данные из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []

# Настройка логирования (чтобы видеть ошибки, если что-то пойдёт не так)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Подключаемся к Google Таблице
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_key.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_url(SHEET_URL).sheet1  # первый лист

# Проверка, что заголовки уже есть, если нет — добавим
HEADERS = ["ID", "Тип", "Модель", "Цена", "Статус", "Описание", "Фото (ID)"]
existing_headers = sheet.row_values(1)
if not existing_headers or existing_headers[:len(HEADERS)] != HEADERS:
    sheet.insert_row(HEADERS, 1)  # вставляем первой строкой

# Возможные статусы
STATUSES = ["в наличии", "продан", "в ремонте"]

# Состояния для пошагового добавления товара
(TYPE, MODEL, PRICE, STATUS, DESCRIPTION, PHOTO) = range(6)

# ----- Клавиатуры (кнопки) -----

def main_keyboard():
    """Главное меню с кнопками."""
    buttons = [
        [KeyboardButton("➕ Добавить товар")],
        [KeyboardButton("📋 Все товары"), KeyboardButton("🔍 Поиск по модели")],
        [KeyboardButton("✏️ Изменить статус"), KeyboardButton("🆘 Помощь")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def status_keyboard():
    """Кнопки для выбора статуса при добавлении."""
    buttons = [[KeyboardButton(s)] for s in STATUSES]
    return ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)

# ----- Вспомогательные функции -----

async def check_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in ADMIN_IDS

def get_all_rows():
    """Возвращает все строки таблицы (кроме заголовка) в виде списка словарей."""
    records = sheet.get_all_records()  # автоматически делает первую строку заголовками
    # Преобразуем в список с индексами, чтобы знать номер строки (для обновления статуса)
    rows = []
    for idx, record in enumerate(records, start=2):  # нумерация строк в таблице (2,3,4...)
        record["_row"] = idx
        rows.append(record)
    return rows

def find_product_by_model(model_query: str):
    """Ищет товары, где модель содержит подстроку (без учёта регистра)."""
    all_rows = get_all_rows()
    results = []
    for row in all_rows:
        if model_query.lower() in row["Модель"].lower():
            results.append(row)
    return results

# ----- Обработчики команд -----

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и показ главного меню."""
    await update.message.reply_text(
        "👋 Добро пожаловать в CRM генераторов и стартеров!\n"
        "Используйте кнопки ниже для работы.",
        reply_markup=main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вывод справки."""
    await update.message.reply_text(
        "📌 *CRM бот*\n\n"
        "➕ *Добавить товар* — пошаговое добавление нового генератора/стартера с фото.\n"
        "📋 *Все товары* — список всех товаров.\n"
        "🔍 *Поиск по модели* — поиск по названию модели.\n"
        "✏️ *Изменить статус* — сменить статус товара (в наличии, продан, в ремонте).\n"
        "🆘 *Помощь* — это сообщение.\n\n"
        "Для администраторов доступна команда /export — ссылка на таблицу.",
        parse_mode="Markdown"
    )

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Только для админов: отправляет ссылку на Google Таблицу."""
    user_id = update.effective_user.id
    if not await check_admin(user_id):
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return
    await update.message.reply_text(f"🔗 Онлайн-таблица: {SHEET_URL}")

# ----- Показ всех товаров -----

async def show_all_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выводит список всех товаров с кнопками подробностей."""
    rows = get_all_rows()
    if not rows:
        await update.message.reply_text("📭 Товаров пока нет.")
        return

    # Создаём inline-кнопки для каждого товара (первые 5, чтобы не засорять чат, можно листать)
    keyboard = []
    for row in rows[:10]:  # ограничим 10, чтобы не было слишком длинного сообщения
        label = f"{row['Модель']} ({row['Статус']}) - {row['Цена']}₽"
        callback_data = f"detail_{row['_row']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])

    if len(rows) > 10:
        keyboard.append([InlineKeyboardButton("Показать ещё...", callback_data="show_more")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 *Все товары:*", reply_markup=reply_markup, parse_mode="Markdown")

async def product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает подробную карточку товара при нажатии на кнопку."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "show_more":
        await query.edit_message_text("Функция листания пока не реализована (можно добавить позже).")
        return

    # Извлекаем номер строки
    row_num = int(data.split("_")[1])
    # Получаем данные строки
    try:
        row_values = sheet.row_values(row_num)
        if len(row_values) < 7:
            await query.edit_message_text("Ошибка: неполные данные.")
            return
        _, typ, model, price, status, desc, photo_id = row_values[:7]  # первый столбец ID
        text = (
            f"*{typ}* — {model}\n"
            f"Цена: {price}₽\n"
            f"Статус: {status}\n"
            f"Описание: {desc}\n"
        )
        # Отправляем фото, если есть ID
        if photo_id and photo_id != "":
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=photo_id, caption=text, parse_mode="Markdown")
        else:
            await query.edit_message_text(text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка при показе деталей: {e}")
        await query.edit_message_text("Не удалось загрузить данные.")

# ----- Добавление товара (Conversation) -----

async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога добавления. Спрашиваем тип."""
    await update.message.reply_text(
        "Выберите тип товара:",
        reply_markup=ReplyKeyboardMarkup([["Генератор", "Стартер"]], one_time_keyboard=True, resize_keyboard=True)
    )
    return TYPE

async def add_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем тип и запрашиваем модель."""
    text = update.message.text
    if text not in ["Генератор", "Стартер"]:
        await update.message.reply_text("Пожалуйста, выберите кнопкой: Генератор или Стартер.")
        return TYPE
    context.user_data["type"] = text
    await update.message.reply_text("Введите модель (например, Bosch 012345):", reply_markup=main_keyboard())  # убираем временную клавиатуру
    return MODEL

async def add_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем модель и запрашиваем цену."""
    model = update.message.text.strip()
    if not model:
        await update.message.reply_text("Модель не может быть пустой. Попробуйте ещё раз.")
        return MODEL
    context.user_data["model"] = model
    await update.message.reply_text("Введите цену (только число, руб.):")
    return PRICE

async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем цену (проверяем, что число) и спрашиваем статус."""
    try:
        price = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Цена должна быть целым числом. Повторите ввод.")
        return PRICE
    context.user_data["price"] = price
    await update.message.reply_text("Выберите статус:", reply_markup=status_keyboard())
    return STATUS

async def add_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем статус и запрашиваем описание."""
    status = update.message.text.strip()
    if status not in STATUSES:
        await update.message.reply_text("Пожалуйста, выберите статус из предложенных кнопок.")
        return STATUS
    context.user_data["status"] = status
    await update.message.reply_text("Введите описание (можно оставить пустым, просто напишите 'нет'):", reply_markup=main_keyboard())
    return DESCRIPTION

async def add_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем описание и запрашиваем фото."""
    desc = update.message.text.strip()
    if desc.lower() in ["нет", "-", "нету", "no"]:
        desc = ""
    context.user_data["description"] = desc
    await update.message.reply_text("Отправьте фотографию товара (или просто напишите 'нет', чтобы пропустить).")
    return PHOTO

async def add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем фото (file_id) или пропускаем, затем записываем всё в таблицу."""
    photo_id = ""
    # Проверяем, что пришло фото или текст "нет"
    if update.message.photo:
        # Берём самое большое качество (последний элемент)
        photo_id = update.message.photo[-1].file_id
    elif update.message.text and update.message.text.strip().lower() in ["нет", "no", "-"]:
        photo_id = ""
    else:
        await update.message.reply_text("Пожалуйста, отправьте именно фото или напишите 'нет'.")
        return PHOTO

    # Собираем все данные
    data = context.user_data
    # Определяем следующий ID (счётчик на основе последней строки)
    all_rows = get_all_rows()
    new_id = max([int(r["ID"]) for r in all_rows if r["ID"].isdigit()] + [0]) + 1

    try:
        # Добавляем строку в таблицу
        sheet.append_row([str(new_id), data["type"], data["model"], str(data["price"]),
                          data["status"], data["description"], photo_id])
        await update.message.reply_text(f"✅ Товар *{data['model']}* успешно добавлен! (ID {new_id})",
                                        parse_mode="Markdown", reply_markup=main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка записи в таблицу: {e}")
        await update.message.reply_text("❌ Не удалось сохранить товар. Проверьте доступ к таблице.",
                                        reply_markup=main_keyboard())

    # Очищаем временные данные
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена добавления."""
    await update.message.reply_text("Добавление отменено.", reply_markup=main_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

# ----- Изменение статуса (пошаговое) -----

async def change_status_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показываем список товаров для выбора."""
    rows = get_all_rows()
    if not rows:
        await update.message.reply_text("Нет товаров для изменения.")
        return

    keyboard = []
    for row in rows:
        label = f"{row['Модель']} ({row['Статус']})"
        callback_data = f"status_{row['_row']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите товар для изменения статуса:", reply_markup=reply_markup)

async def status_select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запоминаем выбранный товар и предлагаем новый статус."""
    query = update.callback_query
    await query.answer()
    data = query.data
    row_num = int(data.split("_")[1])
    context.user_data["edit_row"] = row_num

    keyboard = []
    for s in STATUSES:
        keyboard.append([InlineKeyboardButton(s, callback_data=f"setstatus_{s}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите новый статус:", reply_markup=reply_markup)

async def status_set_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливаем новый статус в таблице."""
    query = update.callback_query
    await query.answer()
    new_status = query.data.split("_")[1]
    row_num = context.user_data.get("edit_row")

    if not row_num:
        await query.edit_message_text("Ошибка сессии. Попробуйте снова.")
        return

    try:
        # Обновляем конкретную ячейку (столбец E = 5-й)
        sheet.update_cell(row_num, 5, new_status)  # Статус - 5-й столбец (A=1, B=2, C=3, D=4, E=5)
        await query.edit_message_text(f"✅ Статус изменён на *{new_status}*.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка обновления статуса: {e}")
        await query.edit_message_text("❌ Не удалось обновить статус.")
    finally:
        context.user_data.pop("edit_row", None)

# ----- Поиск по модели -----

async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрашиваем часть названия модели."""
    await update.message.reply_text("Введите модель или её часть для поиска:", reply_markup=main_keyboard())
    # Устанавливаем состояние, что ожидаем ввод поискового запроса
    return 0  # используем простое состояние, не ConversationHandler

# Обработчик текста для поиска будет вызываться только когда ожидается поиск.
# Проще сделать через отдельный фильтр, но для новичка используем ConversationHandler для поиска.
# Я добавлю ConversationHandler для поиска тоже, с одним состоянием.

# ----- Поиск (Conversation) -----
SEARCH_MODEL = 0

async def search_model_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполняет поиск по введённой подстроке."""
    query = update.message.text.strip()
    if not query:
        await update.message.reply_text("Введите что-нибудь для поиска.")
        return SEARCH_MODEL

    results = find_product_by_model(query)
    if not results:
        await update.message.reply_text("🔍 Ничего не найдено.", reply_markup=main_keyboard())
        return ConversationHandler.END

    # Показываем результаты с кнопками подробностей
    keyboard = []
    for row in results[:5]:  # максимум 5
        label = f"{row['Модель']} ({row['Статус']})"
        callback_data = f"detail_{row['_row']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔍 *Результаты поиска:*", reply_markup=reply_markup, parse_mode="Markdown")
    return ConversationHandler.END

# ----- Обработчик текстовых сообщений (для кнопок главного меню) -----
async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок главного меню и запускает нужные сценарии."""
    text = update.message.text
    if text == "📋 Все товары":
        await show_all_products(update, context)
    elif text == "✏️ Изменить статус":
        await change_status_start(update, context)
    elif text == "🆘 Помощь":
        await help_command(update, context)
    else:
        await update.message.reply_text("Неизвестная команда. Используйте кнопки меню.")
    return

# ----- Главная функция -----

def main():
    """Запуск бота."""
    # Создаём приложение
    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler для добавления товара
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
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_photo)  # для пропуска
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_add)],
    )

    # ConversationHandler для поиска
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Поиск по модели$"), search_start)],
        states={
            SEARCH_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_model_input)],
        },
        fallbacks=[],
    )

    app.add_handler(add_conv)
    app.add_handler(search_conv)

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export", export_command))

    # Обработчики нажатий inline-кнопок
    app.add_handler(CallbackQueryHandler(product_detail, pattern="^detail_"))
    app.add_handler(CallbackQueryHandler(status_select_product, pattern="^status_"))
    app.add_handler(CallbackQueryHandler(status_set_new, pattern="^setstatus_"))
    # Кнопка "показать ещё"
    app.add_handler(CallbackQueryHandler(product_detail, pattern="^show_more"))

    # Обработчик текстовых сообщений из главного меню (кнопки, не вошедшие в Conversation)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))

    # Запуск бота (бесконечный цикл)
    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()