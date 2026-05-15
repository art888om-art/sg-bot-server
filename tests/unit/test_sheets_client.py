"""Tests for the SheetsClient in-memory backend behavior."""

from __future__ import annotations

import asyncio

import pytest

from app.integrations.sheets_client import SheetsClient, safe_cell


def test_safe_cell_escapes_formula_prefixes() -> None:
    assert safe_cell("=SUM(A1)") == "'=SUM(A1)"
    assert safe_cell("+import") == "'+import"
    assert safe_cell("-cmd") == "'-cmd"
    assert safe_cell("@sheet") == "'@sheet"
    assert safe_cell("normal text") == "normal text"
    assert safe_cell("") == ""
    assert safe_cell(None) == ""
    assert safe_cell(42) == "42"


@pytest.mark.asyncio
async def test_in_memory_append_and_read(sheets_client: SheetsClient) -> None:
    await sheets_client.ensure_sheet("TestSheet", ["ID", "Name"])
    await sheets_client.append_row("TestSheet", ["1", "Alice"])
    await sheets_client.append_row("TestSheet", ["2", "Bob"])
    records = await sheets_client.get_all_records("TestSheet")
    assert len(records) == 2
    assert records[0]["Name"] == "Alice"
    assert records[1]["ID"] == "2"


@pytest.mark.asyncio
async def test_next_id_grows(sheets_client: SheetsClient) -> None:
    await sheets_client.ensure_sheet("Ids", ["ID", "X"])
    assert await sheets_client.next_id("Ids") == 1
    await sheets_client.append_row("Ids", ["1", "a"])
    await sheets_client.append_row("Ids", ["5", "b"])
    assert await sheets_client.next_id("Ids") == 6


@pytest.mark.asyncio
async def test_update_by_id(sheets_client: SheetsClient) -> None:
    await sheets_client.ensure_sheet("U", ["ID", "Status"])
    await sheets_client.append_row("U", ["7", "old"])
    ok = await sheets_client.update_by_id("U", "ID", "7", {"Status": "new"})
    assert ok is True
    records = await sheets_client.get_all_records("U")
    assert records[0]["Status"] == "new"


def test_formula_injection_safe_cell_adds_apostrophe() -> None:
    """`safe_cell` is what gets sent to real Google Sheets — it MUST escape."""
    assert safe_cell("=cmd|' /C calc'!A0").startswith("'=")
    assert safe_cell("+SUM(A1)").startswith("'+")
    assert safe_cell("-1+1").startswith("'-")
    assert safe_cell("@import").startswith("'@")
    # Safe values are untouched
    assert safe_cell("hello").startswith("h")


@pytest.mark.asyncio
async def test_concurrent_writes_do_not_lose_rows(sheets_client: SheetsClient) -> None:
    await sheets_client.ensure_sheet("C", ["ID", "Val"])

    async def write(i: int) -> None:
        await sheets_client.append_row("C", [str(i), f"v{i}"])

    await asyncio.gather(*(write(i) for i in range(20)))
    records = await sheets_client.get_all_records("C")
    assert len(records) == 20
