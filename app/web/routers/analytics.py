"""Analytics endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.domain import Manager
from app.services.analytics_service import AnalyticsOverview
from app.services.registry import Services
from app.web.deps import current_manager, get_services_dep

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> AnalyticsOverview:
    return await services.analytics.overview(manager)
