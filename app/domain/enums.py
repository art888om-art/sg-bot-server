"""Enumerations shared across the domain."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Access role for the system."""

    OWNER = "owner"
    MANAGER = "manager"
    VIEWER = "viewer"


class ClientStatus(StrEnum):
    """Lifecycle status of a client."""

    NEW = "Новый"
    IN_PROGRESS = "В работе"
    THINKING = "Думает"
    DEAL = "Сделка"
    REJECTED = "Отказ"


class ProductType(StrEnum):
    GENERATOR = "Генератор"
    STARTER = "Стартер"
    OTHER = "Другое"


class ProductCondition(StrEnum):
    NEW = "Новый"
    USED = "Б/У"
    REFURBISHED = "Восстановленный"


class ProductStatus(StrEnum):
    IN_STOCK = "в наличии"
    SOLD = "продан"
    RESERVED = "резерв"
    REPAIR = "ремонт"


class DealStatus(StrEnum):
    NEW = "Новая"
    IN_PROGRESS = "В обработке"
    PAID = "Оплачена"
    CLOSED = "Закрыта"
    CANCELLED = "Отменена"


class TaskStatus(StrEnum):
    PLANNED = "Запланировано"
    DONE = "Выполнено"
    CANCELLED = "Отменено"
