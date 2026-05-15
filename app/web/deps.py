"""FastAPI dependencies: settings, services, current user, CSRF."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.domain import Manager, Role
from app.services.auth_service import AuthError
from app.services.registry import Services, build_services
from app.web.security import AUTH_COOKIE, verify_csrf


async def get_services_dep(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Services:
    return await build_services(settings)


async def current_manager(
    request: Request,
    services: Annotated[Services, Depends(get_services_dep)],
    auth_token: Annotated[str | None, Cookie(alias=AUTH_COOKIE)] = None,
) -> Manager:
    if not auth_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизован")
    try:
        manager = await services.auth.manager_from_token(auth_token)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    request.state.manager = manager
    return manager


def require_role(
    *allowed: Role,
) -> Callable[[Manager], Awaitable[Manager]]:
    """Dependency factory: enforce one of given roles."""

    async def _checker(manager: Annotated[Manager, Depends(current_manager)]) -> Manager:
        if manager.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return manager

    return _checker


async def csrf_guard(request: Request) -> None:
    """Reject non-safe methods without a matching CSRF token."""
    if not verify_csrf(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid"
        )
