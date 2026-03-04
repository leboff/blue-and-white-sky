"""FastAPI app: describeFeedGenerator and getFeedSkeleton (HN-ranked). Headless JSON API."""

from __future__ import annotations

from fastapi import FastAPI

from .api import admin_router, dev_router, feed_router
from .config import require_bluesky_credentials

require_bluesky_credentials()

app = FastAPI(title="Penn State Football Feed")

app.include_router(feed_router)
app.include_router(admin_router)
app.include_router(dev_router)
