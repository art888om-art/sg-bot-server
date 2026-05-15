"""Domain models — typed business entities."""

from app.domain.client import Client, ClientCreate, ClientUpdate
from app.domain.deal import Deal, DealCreate, DealUpdate
from app.domain.enums import (
    ClientStatus,
    DealStatus,
    ProductCondition,
    ProductStatus,
    ProductType,
    Role,
    TaskStatus,
)
from app.domain.manager import Manager
from app.domain.product import Product, ProductCreate, ProductUpdate
from app.domain.task import Task, TaskCreate, TaskUpdate

__all__ = [
    "Client",
    "ClientCreate",
    "ClientStatus",
    "ClientUpdate",
    "Deal",
    "DealCreate",
    "DealStatus",
    "DealUpdate",
    "Manager",
    "Product",
    "ProductCondition",
    "ProductCreate",
    "ProductStatus",
    "ProductType",
    "ProductUpdate",
    "Role",
    "Task",
    "TaskCreate",
    "TaskStatus",
    "TaskUpdate",
]
