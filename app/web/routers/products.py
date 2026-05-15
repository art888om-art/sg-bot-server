"""Product API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.domain import Manager, Product, ProductCreate, ProductStatus, ProductUpdate
from app.services.auth_service import AuthError
from app.services.registry import Services
from app.web.deps import csrf_guard, current_manager, get_services_dep

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.get("")
async def list_products(
    services: Annotated[Services, Depends(get_services_dep)],
    _manager: Annotated[Manager, Depends(current_manager)],
    q: Annotated[str, Query(max_length=200)] = "",
    status_filter: Annotated[ProductStatus | None, Query(alias="status")] = None,
) -> dict[str, object]:
    products = await services.product_service.list(search=q, status=status_filter)
    return {
        "data": [p.model_dump(mode="json") for p in products],
        "meta": {"total": len(products)},
    }


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(csrf_guard)])
async def create_product(
    payload: ProductCreate,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> Product:
    try:
        return await services.product_service.create(manager, payload)
    except AuthError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.patch("/{product_id}", dependencies=[Depends(csrf_guard)])
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> dict[str, bool]:
    try:
        ok = await services.product_service.update(manager, product_id, payload)
    except AuthError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return {"ok": True}
