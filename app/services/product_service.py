"""Product business logic."""

from __future__ import annotations

from app.domain import Manager, Product, ProductCreate, ProductStatus, ProductUpdate, Role
from app.repositories.product_repo import ProductRepository
from app.services.auth_service import AuthError, AuthService


class ProductService:
    def __init__(self, repo: ProductRepository) -> None:
        self._repo = repo

    async def list(self, search: str = "", status: ProductStatus | None = None) -> list[Product]:
        return await self._repo.list_all(search=search, status=status)

    async def get(self, product_id: int) -> Product | None:
        return await self._repo.find_by_id(product_id)

    async def create(self, manager: Manager, data: ProductCreate) -> Product:
        AuthService.assert_role(manager, Role.OWNER, Role.MANAGER)
        return await self._repo.create(data)

    async def update(self, manager: Manager, product_id: int, data: ProductUpdate) -> bool:
        AuthService.assert_role(manager, Role.OWNER, Role.MANAGER)
        return await self._repo.update(product_id, data)

    async def update_status(self, manager: Manager, product_id: int, status: ProductStatus) -> bool:
        AuthService.assert_role(manager, Role.OWNER, Role.MANAGER)
        return await self._repo.update_status(product_id, status)

    async def delete(self, manager: Manager, product_id: int) -> bool:
        # Soft-delete style: only owners may "delete" (mark as sold/cancelled).
        if manager.role != Role.OWNER:
            raise AuthError("Удаление товара доступно только владельцу")
        return await self._repo.update_status(product_id, ProductStatus.SOLD)
