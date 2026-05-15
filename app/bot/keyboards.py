"""Reply and inline keyboards."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot import texts as T


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=T.BTN_CLIENTS), KeyboardButton(text=T.BTN_PRODUCTS)],
            [KeyboardButton(text=T.BTN_DEALS), KeyboardButton(text=T.BTN_TASKS)],
            [KeyboardButton(text=T.BTN_ANALYTICS), KeyboardButton(text=T.BTN_SEARCH)],
            [KeyboardButton(text=T.BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def clients_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=T.BTN_ADD), KeyboardButton(text=T.BTN_SEARCH)],
            [KeyboardButton(text=T.BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def cancel_only() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=T.BTN_CANCEL)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def client_card_actions(client_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 В работе", callback_data=f"cli:status:{client_id}:В работе"
                ),
                InlineKeyboardButton(
                    text="✅ Сделка", callback_data=f"cli:status:{client_id}:Сделка"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отказ", callback_data=f"cli:status:{client_id}:Отказ"
                ),
            ],
        ]
    )
