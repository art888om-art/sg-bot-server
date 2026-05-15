"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app import __version__
from app.config import get_settings
from app.logging import configure_logging, get_logger
from app.services.auth_service import AuthError
from app.services.registry import build_services
from app.web.routers import analytics, auth, clients, deals, health, pages, products, tasks

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    logger.info("startup", env=settings.env, mode=settings.bot_mode, version=__version__)
    # Eagerly build services so sheets schema is ensured at boot.
    services = await build_services(settings)
    app.state.services = services
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    limiter = Limiter(key_func=get_remote_address)

    app = FastAPI(
        title="AutoCRM",
        version=__version__,
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        lifespan=_lifespan,
    )
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    # Static files
    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

    # Routers
    app.include_router(pages.router)
    app.include_router(auth.router)
    app.include_router(clients.router)
    app.include_router(products.router)
    app.include_router(deals.router)
    app.include_router(tasks.router)
    app.include_router(analytics.router)
    app.include_router(health.router)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMIT", "message": "Слишком много запросов"}},
        )

    @app.exception_handler(AuthError)
    async def _auth_handler(request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "AUTH_ERROR", "message": str(exc)}},
        )

    return app


# Module-level instance for `uvicorn app.web.app:app`
app = create_app()
