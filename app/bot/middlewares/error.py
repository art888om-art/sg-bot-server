"""Global error handler — never leak tracebacks to the user."""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.bot import texts as T
from app.logging import get_logger

logger = get_logger(__name__)


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            logger.exception("bot.handler_error", error=str(exc))
            if isinstance(event, Message):
                with contextlib.suppress(Exception):
                    await event.answer(T.GENERIC_ERROR)
            return None
