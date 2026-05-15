"""Auth middleware — injects current Manager into handler data."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.bot import texts as T
from app.services.registry import Services


class AuthMiddleware(BaseMiddleware):
    """Reject unknown users and put `manager` into handler kwargs."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)
        manager = await self._services.managers.find_by_telegram_id(str(tg_user.id))
        if manager is None or not manager.active:
            if isinstance(event, Message):
                await event.answer(T.ACCESS_DENIED)
            return None
        data["manager"] = manager
        data["services"] = self._services
        return await handler(event, data)
