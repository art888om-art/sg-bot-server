"""Clients router: list, add (FSM), search, status updates."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from pydantic import ValidationError

from app.bot import texts as T
from app.bot.keyboards import cancel_only, client_card_actions, clients_menu, main_menu
from app.bot.states import AddClient
from app.domain import ClientCreate, ClientStatus, Manager
from app.services.registry import Services

router = Router(name="clients")


@router.message(F.text == T.BTN_CLIENTS)
@router.message(Command("clients"))
async def show_clients(message: Message, manager: Manager, services: Services) -> None:
    clients = await services.client_service.list_for(manager)
    if not clients:
        await message.answer("📋 У тебя пока нет клиентов.", reply_markup=clients_menu())
        return
    lines = ["📋 <b>Твои клиенты:</b>"]
    for c in clients[:20]:
        lines.append(f"#{c.id} <b>{c.name}</b> · {c.phone} · {c.status.value}")
    if len(clients) > 20:
        lines.append(f"\n…и ещё {len(clients) - 20}.")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=clients_menu())


# ─── Add client FSM ───
@router.message(F.text == T.BTN_ADD)
async def add_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AddClient.name)
    await message.answer(T.CLIENT_ASK_NAME, parse_mode="HTML", reply_markup=cancel_only())


@router.message(F.text == T.BTN_CANCEL)
async def cancel_any(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(T.CANCELLED, reply_markup=main_menu())


@router.message(AddClient.name)
async def add_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Имя не может быть пустым.")
        return
    await state.update_data(name=text)
    await state.set_state(AddClient.phone)
    await message.answer(T.CLIENT_ASK_PHONE, parse_mode="HTML")


@router.message(AddClient.phone)
async def add_phone(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    # Validate via pydantic
    try:
        # Build a minimal ClientCreate-style dict purely to leverage validator.
        ClientCreate(name="x", phone=raw)
    except ValidationError:
        await message.answer(T.CLIENT_INVALID_PHONE, parse_mode="HTML")
        return
    await state.update_data(phone=raw)
    await state.set_state(AddClient.auto)
    await message.answer(T.CLIENT_ASK_AUTO, parse_mode="HTML")


@router.message(AddClient.auto)
async def add_auto(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    auto = "" if text in ("-", "") else text
    await state.update_data(auto=auto)
    await state.set_state(AddClient.comment)
    await message.answer(T.CLIENT_ASK_COMMENT, parse_mode="HTML")


@router.message(AddClient.comment)
async def add_comment(
    message: Message, state: FSMContext, manager: Manager, services: Services
) -> None:
    text = (message.text or "").strip()
    comment = "" if text in ("-", "") else text
    data = await state.get_data()
    payload = ClientCreate(
        name=data["name"],
        phone=data["phone"],
        auto=data.get("auto", ""),
        comment=comment,
        status=ClientStatus.NEW,
    )
    client = await services.client_service.create(manager, payload)
    await state.clear()
    await message.answer(
        T.CLIENT_SAVED.format(name=client.name, id=client.id),
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
    await message.answer(
        f"<b>{client.name}</b>\n{client.phone}\nСтатус: {client.status.value}",
        parse_mode="HTML",
        reply_markup=client_card_actions(client.id),
    )


@router.callback_query(F.data.startswith("cli:status:"))
async def cb_status(callback: CallbackQuery, manager: Manager, services: Services) -> None:
    """Inline status changer for clients."""
    parts = (callback.data or "").split(":", maxsplit=3)
    if len(parts) != 4:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    try:
        client_id = int(parts[2])
        new_status = ClientStatus(parts[3])
    except (ValueError, KeyError):
        await callback.answer("Некорректный статус", show_alert=True)
        return
    ok = await services.client_service.update_status(manager, client_id, new_status)
    if ok:
        await callback.answer(f"Статус: {new_status.value}", show_alert=False)
        if callback.message is not None and isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(reply_markup=client_card_actions(client_id))
    else:
        await callback.answer("Не удалось обновить", show_alert=True)


@router.message(F.text == T.BTN_BACK)
async def back_to_main(message: Message) -> None:
    await message.answer("Главное меню", reply_markup=main_menu())
