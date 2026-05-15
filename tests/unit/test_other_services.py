"""Tests for product/deal/task/analytics services."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain import (
    DealCreate,
    DealStatus,
    DealUpdate,
    Manager,
    ProductCreate,
    ProductStatus,
    ProductType,
    Role,
    TaskCreate,
)
from app.services.auth_service import AuthError
from app.services.registry import Services


# ─────────────────────────── products ───────────────────────────
@pytest.mark.asyncio
async def test_create_and_list_products(services: Services, owner_manager: Manager) -> None:
    p = await services.product_service.create(
        owner_manager,
        ProductCreate(type=ProductType.GENERATOR, model="Bosch 80A", price=Decimal("4200.00")),
    )
    assert p.id >= 1
    listed = await services.product_service.list()
    assert any(x.id == p.id for x in listed)


@pytest.mark.asyncio
async def test_only_owner_can_delete_product(
    services: Services, owner_manager: Manager, regular_manager: Manager
) -> None:
    p = await services.product_service.create(
        owner_manager, ProductCreate(type=ProductType.STARTER, model="Denso 12V")
    )
    with pytest.raises(AuthError):
        await services.product_service.delete(regular_manager, p.id)
    ok = await services.product_service.delete(owner_manager, p.id)
    assert ok is True


@pytest.mark.asyncio
async def test_product_search(services: Services, owner_manager: Manager) -> None:
    await services.product_service.create(
        owner_manager, ProductCreate(type=ProductType.GENERATOR, model="Valeo XYZ")
    )
    await services.product_service.create(
        owner_manager, ProductCreate(type=ProductType.STARTER, model="Bosch ABC")
    )
    found = await services.product_service.list(search="bosch")
    assert any("Bosch" in p.model for p in found)


@pytest.mark.asyncio
async def test_product_filter_by_status(services: Services, owner_manager: Manager) -> None:
    p = await services.product_service.create(
        owner_manager, ProductCreate(type=ProductType.GENERATOR, model="X")
    )
    await services.product_service.update_status(owner_manager, p.id, ProductStatus.SOLD)
    sold = await services.product_service.list(status=ProductStatus.SOLD)
    assert any(x.id == p.id for x in sold)


# ─────────────────────────── deals ───────────────────────────
@pytest.mark.asyncio
async def test_create_and_close_deal(services: Services, regular_manager: Manager) -> None:
    d = await services.deal_service.create(
        regular_manager,
        DealCreate(client_id=1, amount=Decimal("5000")),
    )
    assert d.id >= 1
    ok = await services.deal_service.update(
        regular_manager, d.id, DealUpdate(status=DealStatus.CLOSED)
    )
    assert ok is True


@pytest.mark.asyncio
async def test_manager_cannot_update_other_managers_deal(
    services: Services, regular_manager: Manager, owner_manager: Manager
) -> None:
    other = await services.managers.upsert("777", "Other", Role.MANAGER)
    other_mgr = await services.managers.find_by_telegram_id(other.telegram_id)
    assert other_mgr is not None
    d = await services.deal_service.create(
        other_mgr, DealCreate(client_id=1, amount=Decimal("100"))
    )
    # regular_manager cannot update other_mgr's deal
    ok = await services.deal_service.update(
        regular_manager, d.id, DealUpdate(status=DealStatus.CANCELLED)
    )
    assert ok is False
    # but owner can
    ok = await services.deal_service.update(
        owner_manager, d.id, DealUpdate(status=DealStatus.CANCELLED)
    )
    assert ok is True


# ─────────────────────────── tasks ───────────────────────────
@pytest.mark.asyncio
async def test_task_create_and_today(services: Services, regular_manager: Manager) -> None:
    await services.task_service.create(
        regular_manager,
        TaskCreate(description="Позвонить клиенту", date=date.today()),
    )
    await services.task_service.create(
        regular_manager,
        TaskCreate(description="Завтрашняя задача", date=date.today() + timedelta(days=1)),
    )
    today = await services.task_service.today(regular_manager)
    assert len(today) == 1
    assert today[0].description == "Позвонить клиенту"


@pytest.mark.asyncio
async def test_mark_task_done(services: Services, regular_manager: Manager) -> None:
    t = await services.task_service.create(
        regular_manager, TaskCreate(description="Х", date=date.today())
    )
    ok = await services.task_service.mark_done(regular_manager, t.id)
    assert ok is True


# ─────────────────────────── analytics ───────────────────────────
@pytest.mark.asyncio
async def test_analytics_overview_counts(services: Services, regular_manager: Manager) -> None:
    overview = await services.analytics.overview(regular_manager)
    assert overview["total_deals"] >= 0
    await services.deal_service.create(
        regular_manager, DealCreate(client_id=1, amount=Decimal("1000"))
    )
    overview2 = await services.analytics.overview(regular_manager)
    assert overview2["total_deals"] == overview["total_deals"] + 1
    assert overview2["total_revenue"] >= 1000.0
