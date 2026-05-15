"""Client API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.domain import Client, ClientCreate, ClientUpdate, Manager
from app.services.registry import Services
from app.web.deps import csrf_guard, current_manager, get_services_dep

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])


@router.get("")
async def list_clients(
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
    q: Annotated[str, Query(max_length=200)] = "",
) -> dict[str, object]:
    clients = (
        await services.client_service.search(manager, q)
        if q
        else await services.client_service.list_for(manager)
    )
    return {"data": [c.model_dump(mode="json") for c in clients], "meta": {"total": len(clients)}}


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(csrf_guard)])
async def create_client(
    payload: ClientCreate,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> Client:
    return await services.client_service.create(manager, payload)


@router.get("/{client_id}")
async def get_client(
    client_id: int,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> Client:
    client = await services.client_service.get(manager, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    return client


@router.patch("/{client_id}", dependencies=[Depends(csrf_guard)])
async def update_client(
    client_id: int,
    payload: ClientUpdate,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> dict[str, bool]:
    ok = await services.client_service.update(manager, client_id, payload)
    if not ok:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    return {"ok": True}
