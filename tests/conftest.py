"""Shared pytest fixtures."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from app.config import Settings, get_settings
from app.domain import Manager, Role
from app.integrations.sheets_client import SheetsClient, reset_sheets_client_for_tests
from app.services.registry import Services, build_services


@pytest.fixture
def event_loop_policy():  # type: ignore[no-untyped-def]
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    """Settings with empty Google Sheet URL — falls back to in-memory backend."""
    monkeypatch.setenv("BOT_TOKEN", "test:token")
    monkeypatch.setenv("GOOGLE_SHEET_URL", "")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", str(tmp_path / "does-not-exist.json"))
    monkeypatch.setenv("JWT_SECRET", "test-secret-very-long-string-1234567890")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("BOT_MODE", "polling")
    get_settings.cache_clear()
    reset_sheets_client_for_tests()
    return get_settings()


@pytest_asyncio.fixture
async def services(settings: Settings) -> AsyncIterator[Services]:
    svc = await build_services(settings)
    yield svc
    reset_sheets_client_for_tests()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def owner_manager(services: Services) -> Manager:
    return await services.managers.upsert("100", "Test Owner", Role.OWNER)


@pytest_asyncio.fixture
async def regular_manager(services: Services) -> Manager:
    return await services.managers.upsert("200", "Test Manager", Role.MANAGER)


@pytest_asyncio.fixture
async def sheets_client(services: Services) -> SheetsClient:
    return services.sheets
