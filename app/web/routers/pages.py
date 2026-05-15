"""Server-rendered Jinja2 pages: login, dashboard, etc."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.domain import Manager
from app.services.auth_service import AuthError
from app.services.registry import Services
from app.web.deps import current_manager, get_services_dep
from app.web.security import AUTH_COOKIE

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "landing.html", {})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {})


@router.get("/dashboard", response_class=HTMLResponse, response_model=None)
async def dashboard(
    request: Request,
    services: Annotated[Services, Depends(get_services_dep)],
) -> HTMLResponse | RedirectResponse:
    token = request.cookies.get(AUTH_COOKIE)
    if not token:
        return RedirectResponse(url="/login", status_code=303)
    try:
        manager = await services.auth.manager_from_token(token)
    except AuthError:
        return RedirectResponse(url="/login", status_code=303)
    overview = await services.analytics.overview(manager)
    tasks = await services.task_service.today(manager)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "manager": manager,
            "overview": overview,
            "tasks_today": tasks,
        },
    )


@router.get("/clients", response_class=HTMLResponse)
async def clients_page(
    request: Request,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> HTMLResponse:
    clients = await services.client_service.list_for(manager)
    return templates.TemplateResponse(
        request, "clients.html", {"manager": manager, "clients": clients}
    )


@router.get("/products", response_class=HTMLResponse)
async def products_page(
    request: Request,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> HTMLResponse:
    products = await services.product_service.list()
    return templates.TemplateResponse(
        request, "products.html", {"manager": manager, "products": products}
    )


@router.get("/deals", response_class=HTMLResponse)
async def deals_page(
    request: Request,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> HTMLResponse:
    deals = await services.deal_service.list_for(manager)
    return templates.TemplateResponse(request, "deals.html", {"manager": manager, "deals": deals})


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    manager: Annotated[Manager, Depends(current_manager)],
    services: Annotated[Services, Depends(get_services_dep)],
) -> HTMLResponse:
    tasks = await services.task_service.list_for(manager)
    return templates.TemplateResponse(request, "tasks.html", {"manager": manager, "tasks": tasks})
