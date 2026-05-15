"""Integration tests for the FastAPI web API."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.domain import Manager
from app.services.registry import Services
from app.web.security import AUTH_COOKIE, CSRF_COOKIE


@pytest_asyncio.fixture
async def client(settings):  # type: ignore[no-untyped-def]
    # Import here so test settings (monkeypatched env) are used by app factory.
    from app.web.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.mark.asyncio
async def test_unauth_clients_returns_401(client: AsyncClient) -> None:
    res = await client.get("/api/v1/clients")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_login_with_invalid_code_returns_401(client: AsyncClient) -> None:
    res = await client.post("/api/v1/auth/login", json={"code": "nope"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_full_flow_login_then_list_clients(
    client: AsyncClient, services: Services, regular_manager: Manager
) -> None:
    code = services.auth.issue_login_token(regular_manager.telegram_id)
    res = await client.post("/api/v1/auth/login", json={"code": code})
    assert res.status_code == 200
    assert AUTH_COOKIE in res.cookies
    assert CSRF_COOKIE in res.cookies

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["telegram_id"] == regular_manager.telegram_id

    listed = await client.get("/api/v1/clients")
    assert listed.status_code == 200
    assert listed.json()["meta"]["total"] >= 0


@pytest.mark.asyncio
async def test_csrf_blocks_write_without_header(
    client: AsyncClient, services: Services, regular_manager: Manager
) -> None:
    code = services.auth.issue_login_token(regular_manager.telegram_id)
    await client.post("/api/v1/auth/login", json={"code": code})
    # Without X-CSRF-Token header → 403
    res = await client.post("/api/v1/clients", json={"name": "X", "phone": "+380501234567"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_csrf_allows_write_with_header(
    client: AsyncClient, services: Services, regular_manager: Manager
) -> None:
    code = services.auth.issue_login_token(regular_manager.telegram_id)
    login = await client.post("/api/v1/auth/login", json={"code": code})
    csrf_value = login.cookies.get(CSRF_COOKIE)
    assert csrf_value is not None
    res = await client.post(
        "/api/v1/clients",
        json={"name": "Ivan", "phone": "+380501234567"},
        headers={"X-CSRF-Token": csrf_value},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "Ivan"


@pytest.mark.asyncio
async def test_healthz_works(client: AsyncClient) -> None:
    res = await client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
