"""Client business logic."""

from __future__ import annotations

from app.domain import Client, ClientCreate, ClientStatus, ClientUpdate, Manager, Role
from app.repositories.client_repo import ClientRepository


class ClientService:
    def __init__(self, repo: ClientRepository) -> None:
        self._repo = repo

    async def list_for(self, manager: Manager) -> list[Client]:
        """Owners see everyone, managers only their own clients."""
        if manager.role == Role.OWNER:
            return await self._repo.list_by_manager(manager_id=None)
        return await self._repo.list_by_manager(manager_id=manager.telegram_id)

    async def search(self, manager: Manager, query: str) -> list[Client]:
        scope = None if manager.role == Role.OWNER else manager.telegram_id
        return await self._repo.search(query, scope)

    async def get(self, manager: Manager, client_id: int) -> Client | None:
        client = await self._repo.find_by_id(client_id)
        if client is None:
            return None
        if manager.role != Role.OWNER and client.manager_id != manager.telegram_id:
            return None
        return client

    async def create(self, manager: Manager, data: ClientCreate) -> Client:
        return await self._repo.create(data, manager.telegram_id)

    async def update(self, manager: Manager, client_id: int, data: ClientUpdate) -> bool:
        client = await self.get(manager, client_id)
        if client is None:
            return False
        return await self._repo.update(client_id, data)

    async def update_status(self, manager: Manager, client_id: int, status: ClientStatus) -> bool:
        client = await self.get(manager, client_id)
        if client is None:
            return False
        return await self._repo.update_status(client_id, status)
