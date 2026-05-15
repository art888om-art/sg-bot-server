"""Deal API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.domain import Deal, DealCreate, DealUpdate, Manager
from app.services.registry import Services
from app.web.deps import csrf_guard, current_manager, get_services_dep

router = APIRouter(prefix="/api/v1/deals", tags=["deals"])


@router.get("")
async def list_deals(
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> dict[str, object]:
    deals = await services.deal_service.list_for(manager)
    return {"data": [d.model_dump(mode="json") for d in deals], "meta": {"total": len(deals)}}


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(csrf_guard)])
async def create_deal(
    payload: DealCreate,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> Deal:
    return await services.deal_service.create(manager, payload)


@router.patch("/{deal_id}", dependencies=[Depends(csrf_guard)])
async def update_deal(
    deal_id: int,
    payload: DealUpdate,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> dict[str, bool]:
    ok = await services.deal_service.update(manager, deal_id, payload)
    if not ok:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    return {"ok": True}
