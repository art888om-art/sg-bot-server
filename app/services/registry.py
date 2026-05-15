"""Application service container — instantiates and holds wired services."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.integrations.sheets_client import SheetsClient, get_sheets_client
from app.logging import get_logger
from app.repositories.client_repo import ClientRepository
from app.repositories.deal_repo import DealRepository
from app.repositories.manager_repo import ManagerRepository
from app.repositories.product_repo import ProductRepository
from app.repositories.schema import ALL_SHEETS
from app.repositories.task_repo import TaskRepository
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthService
from app.services.client_service import ClientService
from app.services.deal_service import DealService
from app.services.product_service import ProductService
from app.services.task_service import TaskService

logger = get_logger(__name__)


@dataclass
class Services:
    """Bundle of all application services for easy injection."""

    settings: Settings
    sheets: SheetsClient
    managers: ManagerRepository
    clients: ClientRepository
    products: ProductRepository
    deals: DealRepository
    tasks: TaskRepository
    auth: AuthService
    client_service: ClientService
    product_service: ProductService
    deal_service: DealService
    task_service: TaskService
    analytics: AnalyticsService


async def build_services(settings: Settings) -> Services:
    """Construct and initialize all services. Idempotent."""
    sheets = await get_sheets_client(settings)
    managers = ManagerRepository(sheets)
    clients = ClientRepository(sheets)
    products = ProductRepository(sheets)
    deals = DealRepository(sheets)
    tasks = TaskRepository(sheets)

    # Ensure all sheets exist & have headers
    for title, headers in ALL_SHEETS.items():
        try:
            await sheets.ensure_sheet(title, headers)
        except Exception as exc:
            logger.warning("sheets.ensure_failed", title=title, error=str(exc))

    # Auto-register owners from env
    from app.domain import Role

    for owner_id in settings.owner_ids_list:
        await managers.upsert(owner_id, name=f"Owner {owner_id}", role=Role.OWNER)

    auth = AuthService(settings, managers)
    return Services(
        settings=settings,
        sheets=sheets,
        managers=managers,
        clients=clients,
        products=products,
        deals=deals,
        tasks=tasks,
        auth=auth,
        client_service=ClientService(clients),
        product_service=ProductService(products),
        deal_service=DealService(deals),
        task_service=TaskService(tasks),
        analytics=AnalyticsService(deals),
    )
