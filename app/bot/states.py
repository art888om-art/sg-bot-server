"""FSM state groups used by the bot."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddClient(StatesGroup):
    name = State()
    phone = State()
    auto = State()
    comment = State()


class SearchClient(StatesGroup):
    query = State()
