"""Product (aggregate / warehouse item) domain models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ProductStatus, ProductType


class ProductBase(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    type: ProductType = ProductType.GENERATOR
    model: str = Field(min_length=1, max_length=200)
    analog: str = Field(default="", max_length=500)
    features: str = Field(default="", max_length=2000)
    price: Decimal | None = None
    status: ProductStatus = ProductStatus.IN_STOCK
    warranty: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=2000)
    photo_id: str = Field(default="", max_length=500)


class ProductCreate(ProductBase):
    """Payload to create a product."""


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    type: ProductType | None = None
    model: str | None = None
    analog: str | None = None
    features: str | None = None
    price: Decimal | None = None
    status: ProductStatus | None = None
    warranty: str | None = None
    description: str | None = None
    photo_id: str | None = None


class Product(ProductBase):
    id: int
    created_at: datetime | None = None
