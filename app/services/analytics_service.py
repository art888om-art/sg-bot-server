"""Analytics service — computes KPIs over deals/calls."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TypedDict

from app.domain import DealStatus, Manager, Role
from app.repositories.deal_repo import DealRepository


class AnalyticsOverview(TypedDict):
    total_revenue: float
    total_deals: int
    month_revenue: float
    month_deals: int
    closed_deals: int


class AnalyticsService:
    def __init__(self, deals: DealRepository) -> None:
        self._deals = deals

    async def overview(self, manager: Manager) -> AnalyticsOverview:
        scope: str | None = None if manager.role == Role.OWNER else manager.telegram_id
        deals = await self._deals.list_by_manager(scope)
        month_prefix = datetime.now(UTC).strftime("%Y-%m")
        total_revenue = sum((d.amount for d in deals), start=Decimal(0))
        month_deals = [
            d for d in deals if d.created_at and d.created_at.strftime("%Y-%m") == month_prefix
        ]
        month_revenue = sum((d.amount for d in month_deals), start=Decimal(0))
        closed = sum(1 for d in deals if d.status in (DealStatus.CLOSED, DealStatus.PAID))
        return AnalyticsOverview(
            total_revenue=float(total_revenue),
            total_deals=len(deals),
            month_revenue=float(month_revenue),
            month_deals=len(month_deals),
            closed_deals=closed,
        )
