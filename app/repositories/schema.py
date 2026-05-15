"""Worksheet schema — single source of truth for sheet names and headers."""

from __future__ import annotations

from typing import Final

# Sheet names
SHEET_MANAGERS: Final = "Менеджеры"
SHEET_CLIENTS: Final = "Клиенты"
SHEET_PRODUCTS: Final = "Товары"
SHEET_DEALS: Final = "Сделки"
SHEET_TASKS: Final = "Задачи"
SHEET_CALLS: Final = "Звонки"
SHEET_SCRIPTS: Final = "Скрипты"

# Header definitions
HEADERS_MANAGERS: Final[list[str]] = [
    "Telegram_ID",
    "Имя",
    "Роль",
    "Активен",
    "Дата_создания",
]

HEADERS_CLIENTS: Final[list[str]] = [
    "ID",
    "Имя",
    "Телефон",
    "Авто",
    "VIN",
    "Агрегат",
    "Тип",
    "Состояние",
    "Цена",
    "Комментарий",
    "Статус",
    "Источник",
    "История",
    "Менеджер_ID",
    "Дата_создания",
    "Дата_обновления",
]

HEADERS_PRODUCTS: Final[list[str]] = [
    "ID",
    "Тип",
    "Модель",
    "Аналог",
    "Характеристики",
    "Цена",
    "Статус",
    "Гарантия",
    "Описание",
    "Фото_ID",
    "Дата_создания",
]

HEADERS_DEALS: Final[list[str]] = [
    "ID",
    "Клиент_ID",
    "Товар_ID",
    "Сумма",
    "Статус",
    "ТТН",
    "Дата_создания",
    "Дата_закрытия",
    "Менеджер_ID",
]

HEADERS_TASKS: Final[list[str]] = [
    "ID",
    "Менеджер_ID",
    "Клиент_ID",
    "Описание",
    "Дата",
    "Время",
    "Статус",
    "Комментарий",
    "Дата_создания",
]

HEADERS_CALLS: Final[list[str]] = [
    "ID",
    "Менеджер_ID",
    "Клиент_ID",
    "Результат",
    "Длительность",
    "Дата",
]

HEADERS_SCRIPTS: Final[list[str]] = [
    "Категория",
    "Возражение",
    "Ответ",
]

ALL_SHEETS: Final[dict[str, list[str]]] = {
    SHEET_MANAGERS: HEADERS_MANAGERS,
    SHEET_CLIENTS: HEADERS_CLIENTS,
    SHEET_PRODUCTS: HEADERS_PRODUCTS,
    SHEET_DEALS: HEADERS_DEALS,
    SHEET_TASKS: HEADERS_TASKS,
    SHEET_CALLS: HEADERS_CALLS,
    SHEET_SCRIPTS: HEADERS_SCRIPTS,
}
