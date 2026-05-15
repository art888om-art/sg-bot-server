"""Deal domain models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DealStatus


class DealBase(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    client_id: int
    product_id: int | None = None
    amount: Decimal = Field(ge=0)
    status: DealStatus = DealStatus.NEW
    ttn: str = Field(default="", max_length=64)


class DealCreate(DealBase):
    pass


class DealUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    amount: Decimal | None = Field(default=None, ge=0)
    status: DealStatus | None = None
    ttn: str | None = None


class Deal(DealBase):
    id: int
    manager_id: str
    created_at: datetime | None = None
    closed_at: datetime | None = None
