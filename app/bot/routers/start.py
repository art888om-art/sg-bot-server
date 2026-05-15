"""Start / help / login commands."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.bot import texts as T
from app.bot.keyboards import main_menu
from app.config import get_settings
from app.domain import Manager
from app.services.registry import Services

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, manager: Manager) -> None:
    await message.answer(
        T.START.format(name=manager.name),
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(T.HELP, parse_mode="HTML", reply_markup=main_menu())


@router.message(Command("login"))
async def cmd_login(message: Message, manager: Manager, services: Services) -> None:
    """Issue a short-lived login code for the web CRM."""
    settings = get_settings()
    code = services.auth.issue_login_token(manager.telegram_id)
    base_url = (
        str(settings.webhook_base_url) if settings.webhook_base_url else "http://localhost:8000"
    )
    await message.answer(
        T.LOGIN_CODE.format(code=code, url=f"{base_url.rstrip('/')}/login"),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
