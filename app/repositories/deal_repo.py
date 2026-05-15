"""Deal repository — reads/writes the Сделки sheet."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import TypeVar

from app.domain import Deal, DealCreate, DealStatus, DealUpdate
from app.integrations.sheets_client import SheetsClient
from app.repositories.schema import HEADERS_DEALS, SHEET_DEALS

E = TypeVar("E", bound=Enum)


class DealRepository:
    def __init__(self, sheets: SheetsClient) -> None:
        self._sheets = sheets

    async def ensure_schema(self) -> None:
        await self._sheets.ensure_sheet(SHEET_DEALS, HEADERS_DEALS)

    async def list_by_manager(self, manager_id: str | None = None) -> list[Deal]:
        records = await self._sheets.get_all_records(SHEET_DEALS)
        result: list[Deal] = []
        for r in records:
            if manager_id and str(r.get("Менеджер_ID", "")).strip() != str(manager_id).strip():
                continue
            deal = self._to_domain(r)
            if deal is not None:
                result.append(deal)
        return result

    async def create(self, data: DealCreate, manager_id: str) -> Deal:
        new_id = await self._sheets.next_id(SHEET_DEALS)
        now_iso = datetime.now(UTC).isoformat(timespec="seconds")
        await self._sheets.append_row(
            SHEET_DEALS,
            [
                str(new_id),
                str(data.client_id),
                str(data.product_id) if data.product_id else "",
                str(data.amount),
                data.status.value,
                data.ttn,
                now_iso,
                "",  # closed_at empty until closed
                str(manager_id),
            ],
        )
        return Deal(
            id=new_id,
            manager_id=str(manager_id),
            created_at=datetime.now(UTC),
            **data.model_dump(),
        )

    async def update(self, deal_id: int, data: DealUpdate) -> bool:
        updates: dict[str, object] = {}
        if data.amount is not None:
            updates["Сумма"] = str(data.amount)
        if data.ttn is not None:
            updates["ТТН"] = data.ttn
        if data.status is not None:
            updates["Статус"] = data.status.value
            if data.status in (DealStatus.CLOSED, DealStatus.CANCELLED, DealStatus.PAID):
                updates["Дата_закрытия"] = datetime.now(UTC).isoformat(timespec="seconds")
        if not updates:
            return True
        return await self._sheets.update_by_id(
            SHEET_DEALS, id_column="ID", id_value=str(deal_id), updates=updates
        )

    @staticmethod
    def _to_domain(r: dict[str, object]) -> Deal | None:
        raw_id = str(r.get("ID", "")).strip()
        raw_client = str(r.get("Клиент_ID", "")).strip()
        if not raw_id.isdigit() or not raw_client.isdigit():
            return None
        product_raw = str(r.get("Товар_ID", "")).strip()
        product_id = int(product_raw) if product_raw.isdigit() else None
        amount = _parse_decimal(r.get("Сумма")) or Decimal(0)
        status = _safe_enum(DealStatus, r.get("Статус")) or DealStatus.NEW
        try:
            return Deal(
                id=int(raw_id),
                client_id=int(raw_client),
                product_id=product_id,
                amount=amount,
                status=status,
                ttn=str(r.get("ТТН", "")).strip(),
                manager_id=str(r.get("Менеджер_ID", "")).strip(),
                created_at=_parse_dt(r.get("Дата_создания")),
                closed_at=_parse_dt(r.get("Дата_закрытия")),
            )
        except Exception:
            return None


def _parse_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ".").strip())
    except InvalidOperation:
        return None


def _parse_dt(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _safe_enum[E: Enum](enum_cls: type[E], value: object) -> E | None:
    if value is None or value == "":
        return None
    try:
        return enum_cls(str(value).strip())
    except ValueError:
        return None
