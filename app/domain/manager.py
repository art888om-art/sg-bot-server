"""Manager — a system user (sales rep, owner, or viewer)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Role


class Manager(BaseModel):
    """A registered user of the CRM."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    telegram_id: str = Field(description="Telegram numeric ID as string.")
    name: str
    role: Role = Role.MANAGER
    active: bool = True
    created_at: datetime | None = None
