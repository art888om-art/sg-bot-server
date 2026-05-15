"""Tests for AuthService — JWT and login codes."""

from __future__ import annotations

import pytest

from app.domain import Manager, Role
from app.services.auth_service import AuthError
from app.services.registry import Services


@pytest.mark.asyncio
async def test_issue_and_decode_token(services: Services, owner_manager: Manager) -> None:
    token = services.auth.issue_token(owner_manager)
    payload = services.auth.decode_token(token)
    assert payload["sub"] == owner_manager.telegram_id
    assert payload["role"] == Role.OWNER.value


@pytest.mark.asyncio
async def test_invalid_token_rejected(services: Services) -> None:
    with pytest.raises(AuthError):
        services.auth.decode_token("not-a-jwt")


@pytest.mark.asyncio
async def test_login_token_one_time(services: Services, regular_manager: Manager) -> None:
    code = services.auth.issue_login_token(regular_manager.telegram_id)
    manager = await services.auth.exchange_login_token(code)
    assert manager.telegram_id == regular_manager.telegram_id
    # Second use must fail
    with pytest.raises(AuthError):
        await services.auth.exchange_login_token(code)


@pytest.mark.asyncio
async def test_login_token_unknown_user_rejected(services: Services) -> None:
    code = services.auth.issue_login_token("nobody")
    with pytest.raises(AuthError):
        await services.auth.exchange_login_token(code)
