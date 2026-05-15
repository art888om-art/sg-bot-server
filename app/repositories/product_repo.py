"""Product repository — reads/writes the Товары sheet."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import TypeVar

from app.domain import Product, ProductCreate, ProductStatus, ProductType, ProductUpdate
from app.integrations.sheets_client import SheetsClient
from app.repositories.schema import HEADERS_PRODUCTS, SHEET_PRODUCTS

E = TypeVar("E", bound=Enum)


class ProductRepository:
    def __init__(self, sheets: SheetsClient) -> None:
        self._sheets = sheets

    async def ensure_schema(self) -> None:
        await self._sheets.ensure_sheet(SHEET_PRODUCTS, HEADERS_PRODUCTS)

    async def list_all(
        self, search: str = "", status: ProductStatus | None = None
    ) -> list[Product]:
        records = await self._sheets.get_all_records(SHEET_PRODUCTS)
        products = [p for p in (self._to_domain(r) for r in records) if p is not None]
        if status is not None:
            products = [p for p in products if p.status == status]
        if search:
            q = search.lower().strip()
            products = [
                p
                for p in products
                if q in p.model.lower() or q in p.type.value.lower() or q in p.analog.lower()
            ]
        return products

    async def find_by_id(self, product_id: int) -> Product | None:
        records = await self._sheets.get_all_records(SHEET_PRODUCTS)
        for r in records:
            if str(r.get("ID", "")).strip() == str(product_id):
                return self._to_domain(r)
        return None

    async def create(self, data: ProductCreate) -> Product:
        new_id = await self._sheets.next_id(SHEET_PRODUCTS)
        now_iso = datetime.now(UTC).isoformat(timespec="seconds")
        await self._sheets.append_row(
            SHEET_PRODUCTS,
            [
                str(new_id),
                data.type.value,
                data.model,
                data.analog,
                data.features,
                str(data.price) if data.price is not None else "",
                data.status.value,
                data.warranty,
                data.description,
                data.photo_id,
                now_iso,
            ],
        )
        return Product(id=new_id, created_at=datetime.now(UTC), **data.model_dump())

    async def update(self, product_id: int, data: ProductUpdate) -> bool:
        updates: dict[str, object] = {}
        if data.type is not None:
            updates["Тип"] = data.type.value
        if data.model is not None:
            updates["Модель"] = data.model
        if data.analog is not None:
            updates["Аналог"] = data.analog
        if data.features is not None:
            updates["Характеристики"] = data.features
        if data.price is not None:
            updates["Цена"] = str(data.price)
        if data.status is not None:
            updates["Статус"] = data.status.value
        if data.warranty is not None:
            updates["Гарантия"] = data.warranty
        if data.description is not None:
            updates["Описание"] = data.description
        if data.photo_id is not None:
            updates["Фото_ID"] = data.photo_id
        if not updates:
            return True
        return await self._sheets.update_by_id(
            SHEET_PRODUCTS, id_column="ID", id_value=str(product_id), updates=updates
        )

    async def update_status(self, product_id: int, new_status: ProductStatus) -> bool:
        return await self._sheets.update_by_id(
            SHEET_PRODUCTS,
            id_column="ID",
            id_value=str(product_id),
            updates={"Статус": new_status.value},
        )

    @staticmethod
    def _to_domain(r: dict[str, object]) -> Product | None:
        raw_id = str(r.get("ID", "")).strip()
        if not raw_id.isdigit():
            return None
        try:
            type_ = _safe_enum(ProductType, r.get("Тип")) or ProductType.OTHER
            status = _safe_enum(ProductStatus, r.get("Статус")) or ProductStatus.IN_STOCK
            return Product(
                id=int(raw_id),
                type=type_,
                model=str(r.get("Модель", "")).strip() or "—",
                analog=str(r.get("Аналог", "")).strip(),
                features=str(r.get("Характеристики", "")).strip(),
                price=_parse_decimal(r.get("Цена")),
                status=status,
                warranty=str(r.get("Гарантия", "")).strip(),
                description=str(r.get("Описание", "")).strip(),
                photo_id=str(r.get("Фото_ID", "")).strip(),
                created_at=_parse_dt(r.get("Дата_создания")),
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
