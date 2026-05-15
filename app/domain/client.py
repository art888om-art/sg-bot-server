"""Client domain models."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import ClientStatus, ProductCondition, ProductType

# Ukrainian phone format. Accepts +380XXXXXXXXX (12 digits after +).
_PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{7,20}$")
_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)


def _normalize_phone(value: str) -> str:
    """Normalize phone to digits-only with leading +.

    Accepts +380501234567, 380501234567, 0501234567 (assumes UA), etc.
    """
    cleaned = re.sub(r"[^\d+]", "", value or "")
    if not cleaned:
        return ""
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("380") and len(cleaned) == 12:
        return f"+{cleaned}"
    if cleaned.startswith("0") and len(cleaned) == 10:
        return f"+38{cleaned}"
    return f"+{cleaned}"


class ClientBase(BaseModel):
    """Shared fields between create/update/read models."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=32)
    auto: str = Field(default="", max_length=200)
    vin: str = Field(default="", max_length=17)
    unit: str = Field(default="", max_length=200, description="Aggregate/model id or text.")
    unit_type: ProductType | None = None
    condition: ProductCondition | None = None
    price: Decimal | None = None
    comment: str = Field(default="", max_length=2000)
    status: ClientStatus = ClientStatus.NEW
    source: str = Field(default="", max_length=100)

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v: object) -> str:
        if v is None:
            return ""
        s = str(v)
        if not _PHONE_RE.match(s):
            raise ValueError("Некорректный номер телефона")
        return _normalize_phone(s)

    @field_validator("vin", mode="before")
    @classmethod
    def _validate_vin(cls, v: object) -> str:
        if v is None or v == "":
            return ""
        s = str(v).strip().upper()
        if not _VIN_RE.match(s):
            raise ValueError("VIN должен содержать 17 символов (без I, O, Q)")
        return s


class ClientCreate(ClientBase):
    """Payload to create a new client."""


class ClientUpdate(BaseModel):
    """Partial update payload."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str | None = None
    phone: str | None = None
    auto: str | None = None
    vin: str | None = None
    unit: str | None = None
    unit_type: ProductType | None = None
    condition: ProductCondition | None = None
    price: Decimal | None = None
    comment: str | None = None
    status: ClientStatus | None = None
    source: str | None = None


class Client(ClientBase):
    """Full client record as stored."""

    id: int
    history: str = ""
    manager_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
