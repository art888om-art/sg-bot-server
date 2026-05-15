"""Tests for ClientService — RBAC and CRUD."""

from __future__ import annotations

import pytest

from app.domain import ClientCreate, ClientStatus, Manager
from app.services.registry import Services


@pytest.mark.asyncio
async def test_create_and_list_own_clients(services: Services, regular_manager: Manager) -> None:
    payload = ClientCreate(name="Иван", phone="+380501234567")
    client = await services.client_service.create(regular_manager, payload)
    assert client.id >= 1
    assert client.name == "Иван"
    listed = await services.client_service.list_for(regular_manager)
    assert any(c.id == client.id for c in listed)


@pytest.mark.asyncio
async def test_manager_cannot_see_other_clients(
    services: Services, regular_manager: Manager, owner_manager: Manager
) -> None:
    other = await services.managers.upsert("999", "Other Manager")
    other_manager = await services.managers.find_by_telegram_id(other.telegram_id)
    assert other_manager is not None
    await services.client_service.create(
        other_manager, ClientCreate(name="Secret", phone="+380501112233")
    )
    visible = await services.client_service.list_for(regular_manager)
    assert all(c.name != "Secret" for c in visible)

    # Owner can see everything
    all_clients = await services.client_service.list_for(owner_manager)
    assert any(c.name == "Secret" for c in all_clients)


@pytest.mark.asyncio
async def test_update_status_changes_value(services: Services, regular_manager: Manager) -> None:
    c = await services.client_service.create(
        regular_manager, ClientCreate(name="Петр", phone="+380501112233")
    )
    ok = await services.client_service.update_status(regular_manager, c.id, ClientStatus.DEAL)
    assert ok is True
    refreshed = await services.client_service.get(regular_manager, c.id)
    assert refreshed is not None
    assert refreshed.status == ClientStatus.DEAL


@pytest.mark.asyncio
async def test_invalid_phone_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ClientCreate(name="Bad", phone="!@#$%")
