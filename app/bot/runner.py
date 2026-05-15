"""Telegram bot setup — Dispatcher + Bot construction and start helpers."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.middlewares.auth import AuthMiddleware
from app.bot.middlewares.error import ErrorMiddleware
from app.bot.routers import clients_router, start_router
from app.config import Settings
from app.logging import get_logger
from app.services.registry import Services

logger = get_logger(__name__)


def build_bot(settings: Settings) -> Bot:
    """Construct a Bot instance with sensible defaults."""
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher(services: Services) -> Dispatcher:
    """Wire up dispatcher with routers and middlewares."""
    dp = Dispatcher(storage=MemoryStorage())

    # Error middleware first so it wraps everything else.
    dp.message.middleware(ErrorMiddleware())
    dp.callback_query.middleware(ErrorMiddleware())

    # Auth middleware injects `manager` and `services`.
    auth_mw = AuthMiddleware(services)
    dp.message.middleware(auth_mw)
    dp.callback_query.middleware(auth_mw)

    # Routers
    dp.include_router(start_router)
    dp.include_router(clients_router)
    return dp


async def run_polling(settings: Settings, services: Services) -> None:
    """Run the bot in long-polling mode (development)."""
    bot = build_bot(settings)
    dp = build_dispatcher(services)
    logger.info("bot.polling.start")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
