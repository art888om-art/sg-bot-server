"""Application entrypoint.

In production (Render) we run `uvicorn app.main:app`. The web app starts the
bot in webhook mode during its lifespan.

For local development run `python -m app.main polling` to start the bot in
long-polling mode without webhooks. Useful when there is no public HTTPS URL.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Request

from app import __version__
from app.bot.runner import build_bot, build_dispatcher, run_polling
from app.config import get_settings
from app.logging import configure_logging, get_logger
from app.services.registry import build_services
from app.web.app import create_app

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
    """Lifespan that wires services and (optionally) bot webhook."""
    settings = get_settings()
    configure_logging()
    logger.info("startup", env=settings.env, mode=settings.bot_mode, version=__version__)

    services = await build_services(settings)
    fastapi_app.state.services = services

    bot: Bot | None = None
    dp: Dispatcher | None = None
    if settings.bot_mode == "webhook" and settings.bot_token:
        bot = build_bot(settings)
        dp = build_dispatcher(services)
        fastapi_app.state.bot = bot
        fastapi_app.state.dp = dp
        if settings.webhook_base_url:
            url = f"{str(settings.webhook_base_url).rstrip('/')}{settings.webhook_path}"
            try:
                await bot.set_webhook(
                    url=url,
                    secret_token=settings.webhook_secret or None,
                    drop_pending_updates=True,
                    allowed_updates=dp.resolve_used_update_types(),
                )
                logger.info("bot.webhook.set", url=url)
            except Exception as exc:
                logger.error("bot.webhook.set_failed", error=str(exc))

    try:
        yield
    finally:
        if bot is not None:
            with suppress(Exception):
                await bot.delete_webhook(drop_pending_updates=False)
            await bot.session.close()
        logger.info("shutdown")


def create_full_app() -> FastAPI:
    """Build the FastAPI app with bot wiring."""
    fastapi_app = create_app()
    # Override the bare lifespan from create_app with our wired lifespan
    fastapi_app.router.lifespan_context = _lifespan
    settings = get_settings()

    if settings.bot_mode == "webhook" and settings.bot_token:

        @fastapi_app.post(settings.webhook_path, include_in_schema=False)
        async def telegram_webhook(request: Request) -> dict[str, bool]:
            secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if settings.webhook_secret and secret_header != settings.webhook_secret:
                logger.warning("webhook.invalid_secret")
                return {"ok": False}
            bot: Bot = request.app.state.bot
            dp: Dispatcher = request.app.state.dp
            payload = await request.json()
            update = Update.model_validate(payload)
            await dp.feed_update(bot, update)
            return {"ok": True}

    return fastapi_app


# Uvicorn entrypoint
app = create_full_app()


async def _polling_main() -> None:
    configure_logging()
    settings = get_settings()
    errors = settings.validate_for_production() if settings.is_production else []
    if errors:
        for err in errors:
            logger.error("config.invalid", error=err)
        sys.exit(1)
    services = await build_services(settings)
    await run_polling(settings, services)


def main() -> None:
    """CLI entry: `python -m app.main polling` to run bot in polling mode."""
    if len(sys.argv) > 1 and sys.argv[1] == "polling":
        asyncio.run(_polling_main())
        return
    print(
        "Use `uvicorn app.main:app --host 0.0.0.0 --port 8000` to start web+bot (webhook), "
        "or `python -m app.main polling` to run bot in polling mode."
    )


if __name__ == "__main__":
    main()
