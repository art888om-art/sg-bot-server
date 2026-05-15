"""Deal business logic."""

from __future__ import annotations

from app.domain import Deal, DealCreate, DealUpdate, Manager, Role
from app.repositories.deal_repo import DealRepository


class DealService:
    def __init__(self, repo: DealRepository) -> None:
        self._repo = repo

    async def list_for(self, manager: Manager) -> list[Deal]:
        if manager.role == Role.OWNER:
            return await self._repo.list_by_manager(manager_id=None)
        return await self._repo.list_by_manager(manager_id=manager.telegram_id)

    async def create(self, manager: Manager, data: DealCreate) -> Deal:
        return await self._repo.create(data, manager.telegram_id)

    async def update(self, manager: Manager, deal_id: int, data: DealUpdate) -> bool:
        # In a richer model we'd check that the deal belongs to manager; for
        # MVP owners can edit any deal, managers only their own.
        deals = await self._repo.list_by_manager(manager.telegram_id)
        if manager.role != Role.OWNER and not any(d.id == deal_id for d in deals):
            return False
        return await self._repo.update(deal_id, data)
