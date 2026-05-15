"""Bot routers grouped by feature."""

from app.bot.routers.clients import router as clients_router
from app.bot.routers.start import router as start_router

__all__ = ["clients_router", "start_router"]
