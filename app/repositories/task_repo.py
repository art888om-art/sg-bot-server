"""Task repository — reads/writes the Задачи sheet."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import Enum
from typing import TypeVar

from app.domain import Task, TaskCreate, TaskStatus, TaskUpdate
from app.integrations.sheets_client import SheetsClient
from app.repositories.schema import HEADERS_TASKS, SHEET_TASKS

E = TypeVar("E", bound=Enum)


class TaskRepository:
    def __init__(self, sheets: SheetsClient) -> None:
        self._sheets = sheets

    async def ensure_schema(self) -> None:
        await self._sheets.ensure_sheet(SHEET_TASKS, HEADERS_TASKS)

    async def list_by_manager(
        self, manager_id: str | None = None, on_date: date | None = None
    ) -> list[Task]:
        records = await self._sheets.get_all_records(SHEET_TASKS)
        result: list[Task] = []
        for r in records:
            task = self._to_domain(r)
            if task is None:
                continue
            if manager_id and task.manager_id != str(manager_id):
                continue
            if on_date is not None and task.date != on_date:
                continue
            result.append(task)
        return result

    async def create(self, data: TaskCreate, manager_id: str) -> Task:
        new_id = await self._sheets.next_id(SHEET_TASKS)
        now_iso = datetime.now(UTC).isoformat(timespec="seconds")
        await self._sheets.append_row(
            SHEET_TASKS,
            [
                str(new_id),
                str(manager_id),
                str(data.client_id) if data.client_id else "",
                data.description,
                data.date.isoformat(),
                data.time.isoformat(timespec="minutes") if data.time else "",
                data.status.value,
                data.comment,
                now_iso,
            ],
        )
        return Task(
            id=new_id,
            manager_id=str(manager_id),
            created_at=datetime.now(UTC),
            **data.model_dump(),
        )

    async def update(self, task_id: int, data: TaskUpdate) -> bool:
        updates: dict[str, object] = {}
        if data.description is not None:
            updates["Описание"] = data.description
        if data.date is not None:
            updates["Дата"] = data.date.isoformat()
        if data.time is not None:
            updates["Время"] = data.time.isoformat(timespec="minutes")
        if data.status is not None:
            updates["Статус"] = data.status.value
        if data.comment is not None:
            updates["Комментарий"] = data.comment
        if not updates:
            return True
        return await self._sheets.update_by_id(
            SHEET_TASKS, id_column="ID", id_value=str(task_id), updates=updates
        )

    @staticmethod
    def _to_domain(r: dict[str, object]) -> Task | None:
        raw_id = str(r.get("ID", "")).strip()
        if not raw_id.isdigit():
            return None
        date_str = str(r.get("Дата", "")).strip()
        if not date_str:
            return None
        try:
            task_date = date.fromisoformat(date_str)
        except ValueError:
            return None
        time_str = str(r.get("Время", "")).strip()
        task_time: time | None
        try:
            task_time = time.fromisoformat(time_str) if time_str else None
        except ValueError:
            task_time = None
        client_raw = str(r.get("Клиент_ID", "")).strip()
        client_id = int(client_raw) if client_raw.isdigit() else None
        status = _safe_enum(TaskStatus, r.get("Статус")) or TaskStatus.PLANNED
        try:
            return Task(
                id=int(raw_id),
                manager_id=str(r.get("Менеджер_ID", "")).strip(),
                client_id=client_id,
                description=str(r.get("Описание", "")).strip(),
                date=task_date,
                time=task_time,
                status=status,
                comment=str(r.get("Комментарий", "")).strip(),
                created_at=_parse_dt(r.get("Дата_создания")),
            )
        except Exception:
            return None


def _parse_dt(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _safe_enum[E: Enum](enum_cls: type[E], value: object) -> E | None:
    if value is None or value == "":
        return None
    try:
        return enum_cls(str(value).strip())
    except ValueError:
        return None
