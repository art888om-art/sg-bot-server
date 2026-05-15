"""Client repository — reads/writes the Клиенты sheet."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import TypeVar

from app.domain import (
    Client,
    ClientCreate,
    ClientStatus,
    ClientUpdate,
    ProductCondition,
    ProductType,
)
from app.integrations.sheets_client import SheetsClient
from app.repositories.schema import HEADERS_CLIENTS, SHEET_CLIENTS

E = TypeVar("E", bound=Enum)


class ClientRepository:
    """CRUD on the Clients sheet."""

    def __init__(self, sheets: SheetsClient) -> None:
        self._sheets = sheets

    async def ensure_schema(self) -> None:
        await self._sheets.ensure_sheet(SHEET_CLIENTS, HEADERS_CLIENTS)

    async def list_by_manager(self, manager_id: str | None = None) -> list[Client]:
        records = await self._sheets.get_all_records(SHEET_CLIENTS)
        result: list[Client] = []
        for r in records:
            if manager_id and str(r.get("Менеджер_ID", "")).strip() != str(manager_id).strip():
                continue
            client = self._to_domain(r)
            if client is not None:
                result.append(client)
        return result

    async def find_by_id(self, client_id: int) -> Client | None:
        records = await self._sheets.get_all_records(SHEET_CLIENTS)
        for r in records:
            if str(r.get("ID", "")).strip() == str(client_id):
                return self._to_domain(r)
        return None

    async def create(self, data: ClientCreate, manager_id: str) -> Client:
        new_id = await self._sheets.next_id(SHEET_CLIENTS)
        now_iso = datetime.now(UTC).isoformat(timespec="seconds")
        await self._sheets.append_row(
            SHEET_CLIENTS,
            [
                str(new_id),
                data.name,
                data.phone,
                data.auto,
                data.vin,
                data.unit,
                data.unit_type.value if data.unit_type else "",
                data.condition.value if data.condition else "",
                str(data.price) if data.price is not None else "",
                data.comment,
                data.status.value,
                data.source,
                "",  # History starts empty
                str(manager_id),
                now_iso,
                now_iso,
            ],
        )
        return Client(
            id=new_id,
            manager_id=str(manager_id),
            history="",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            **data.model_dump(),
        )

    async def update(self, client_id: int, data: ClientUpdate) -> bool:
        updates: dict[str, object] = {}
        if data.name is not None:
            updates["Имя"] = data.name
        if data.phone is not None:
            updates["Телефон"] = data.phone
        if data.auto is not None:
            updates["Авто"] = data.auto
        if data.vin is not None:
            updates["VIN"] = data.vin
        if data.unit is not None:
            updates["Агрегат"] = data.unit
        if data.unit_type is not None:
            updates["Тип"] = data.unit_type.value
        if data.condition is not None:
            updates["Состояние"] = data.condition.value
        if data.price is not None:
            updates["Цена"] = str(data.price)
        if data.comment is not None:
            updates["Комментарий"] = data.comment
        if data.status is not None:
            updates["Статус"] = data.status.value
        if data.source is not None:
            updates["Источник"] = data.source
        if not updates:
            return True
        updates["Дата_обновления"] = datetime.now(UTC).isoformat(timespec="seconds")
        return await self._sheets.update_by_id(
            SHEET_CLIENTS, id_column="ID", id_value=str(client_id), updates=updates
        )

    async def update_status(self, client_id: int, new_status: ClientStatus) -> bool:
        return await self._sheets.update_by_id(
            SHEET_CLIENTS,
            id_column="ID",
            id_value=str(client_id),
            updates={
                "Статус": new_status.value,
                "Дата_обновления": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )

    async def search(self, query: str, manager_id: str | None = None) -> list[Client]:
        q = query.lower().strip()
        if not q:
            return await self.list_by_manager(manager_id)
        clients = await self.list_by_manager(manager_id)
        return [
            c
            for c in clients
            if q in c.name.lower()
            or q in c.phone.lower()
            or q in c.vin.lower()
            or q in c.auto.lower()
        ]

    # ─────────────────────────── mapping ───────────────────────────
    @staticmethod
    def _to_domain(r: dict[str, object]) -> Client | None:
        raw_id = str(r.get("ID", "")).strip()
        if not raw_id.isdigit():
            return None
        price = _parse_decimal(r.get("Цена"))
        try:
            return Client(
                id=int(raw_id),
                name=str(r.get("Имя", "")).strip(),
                phone=str(r.get("Телефон", "") or "+0000000"),
                auto=str(r.get("Авто", "")).strip(),
                vin=str(r.get("VIN", "")).strip(),
                unit=str(r.get("Агрегат", "")).strip(),
                unit_type=_safe_enum(ProductType, r.get("Тип")),
                condition=_safe_enum(ProductCondition, r.get("Состояние")),
                price=price,
                comment=str(r.get("Комментарий", "")).strip(),
                status=_safe_enum(ClientStatus, r.get("Статус")) or ClientStatus.NEW,
                source=str(r.get("Источник", "")).strip(),
                history=str(r.get("История", "")).strip(),
                manager_id=str(r.get("Менеджер_ID", "")).strip(),
                created_at=_parse_dt(r.get("Дата_создания")),
                updated_at=_parse_dt(r.get("Дата_обновления")),
            )
        except Exception:
            return None


def _parse_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    s = str(value).replace(",", ".").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_dt(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _safe_enum[E: Enum](enum_cls: type[E], value: object) -> E | None:
    if value is None or value == "":
        return None
    try:
        return enum_cls(str(value).strip())
    except ValueError:
        return None
