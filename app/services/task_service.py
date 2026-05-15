"""Task business logic."""

from __future__ import annotations

from datetime import date

from app.domain import Manager, Task, TaskCreate, TaskStatus, TaskUpdate
from app.repositories.task_repo import TaskRepository


class TaskService:
    def __init__(self, repo: TaskRepository) -> None:
        self._repo = repo

    async def list_for(self, manager: Manager, on_date: date | None = None) -> list[Task]:
        return await self._repo.list_by_manager(manager.telegram_id, on_date=on_date)

    async def today(self, manager: Manager) -> list[Task]:
        return await self.list_for(manager, on_date=date.today())

    async def create(self, manager: Manager, data: TaskCreate) -> Task:
        return await self._repo.create(data, manager.telegram_id)

    async def mark_done(self, manager: Manager, task_id: int) -> bool:
        # Verify ownership by listing manager's tasks
        tasks = await self._repo.list_by_manager(manager.telegram_id)
        if not any(t.id == task_id for t in tasks):
            return False
        return await self._repo.update(task_id, TaskUpdate(status=TaskStatus.DONE))
