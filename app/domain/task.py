"""Task domain models."""

from __future__ import annotations

from datetime import date as date_t
from datetime import datetime
from datetime import time as time_t

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import TaskStatus


class TaskBase(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=2000)
    date: date_t
    time: time_t | None = None
    status: TaskStatus = TaskStatus.PLANNED
    comment: str = Field(default="", max_length=2000)
    client_id: int | None = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    description: str | None = None
    date: date_t | None = None
    time: time_t | None = None
    status: TaskStatus | None = None
    comment: str | None = None


class Task(TaskBase):
    id: int
    manager_id: str
    created_at: datetime | None = None
