"""Task API endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.domain import Manager, Task, TaskCreate
from app.services.registry import Services
from app.web.deps import csrf_guard, current_manager, get_services_dep

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
    on_date: Annotated[date | None, Query(alias="date")] = None,
) -> dict[str, object]:
    tasks = await services.task_service.list_for(manager, on_date=on_date)
    return {"data": [t.model_dump(mode="json") for t in tasks], "meta": {"total": len(tasks)}}


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(csrf_guard)])
async def create_task(
    payload: TaskCreate,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> Task:
    return await services.task_service.create(manager, payload)
