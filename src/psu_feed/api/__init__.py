"""API routers for feed, admin, and dev endpoints."""

from .admin import router as admin_router
from .dev import router as dev_router
from .feed import router as feed_router

__all__ = ["admin_router", "dev_router", "feed_router"]
