"""Liveness and readiness probes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.services.registry import Services
from app.web.deps import get_services_dep

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe — always 200 if the process is alive."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    services: Annotated[Services, Depends(get_services_dep)],
) -> dict[str, str | bool]:
    """Readiness probe — checks Sheets connectivity."""
    ok = await services.sheets.healthcheck()
    return {"status": "ok" if ok else "degraded", "sheets": ok}
