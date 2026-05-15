"""Auth router — login by short-lived code from the bot, logout, /me."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.domain import Manager
from app.services.auth_service import AuthError
from app.services.registry import Services
from app.web.deps import current_manager, get_services_dep
from app.web.security import AUTH_COOKIE, CSRF_COOKIE, cookie_kwargs, issue_csrf_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    code: str


class MeResponse(BaseModel):
    telegram_id: str
    name: str
    role: str


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    services: Annotated[Services, Depends(get_services_dep)],
) -> MeResponse:
    """Exchange a one-time code (from the bot) for a session cookie."""
    try:
        manager = await services.auth.exchange_login_token(body.code)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e

    token = services.auth.issue_token(manager)
    csrf = issue_csrf_token()
    cookie_opts = cookie_kwargs(services.settings)
    response.set_cookie(AUTH_COOKIE, token, **cookie_opts)  # type: ignore[arg-type]
    # CSRF cookie must be readable from JS so the SPA can send it back in a header.
    csrf_opts = dict(cookie_opts)
    csrf_opts["httponly"] = False
    response.set_cookie(CSRF_COOKIE, csrf, **csrf_opts)  # type: ignore[arg-type]
    return MeResponse(telegram_id=manager.telegram_id, name=manager.name, role=manager.role.value)


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(AUTH_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(manager: Annotated[Manager, Depends(current_manager)]) -> MeResponse:
    return MeResponse(telegram_id=manager.telegram_id, name=manager.name, role=manager.role.value)
