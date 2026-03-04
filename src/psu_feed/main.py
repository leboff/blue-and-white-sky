"""FastAPI app: describeFeedGenerator and getFeedSkeleton (HN-ranked). Headless JSON API."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import admin_router, dev_router, feed_router
from .config import require_bluesky_credentials

require_bluesky_credentials()

app = FastAPI(title="Penn State Football Feed")

app.include_router(feed_router)
app.include_router(admin_router)
app.include_router(dev_router)

# SPA at /admin (Dokploy): serve built frontend from STATIC_DIR (default /app/static in Docker)
_STATIC_DIR = Path(os.environ.get("STATIC_DIR", "") or str(Path(__file__).resolve().parent.parent.parent / "static"))
if _STATIC_DIR.exists():
    _index_path = _STATIC_DIR / "index.html"
    if _index_path.exists():
        _assets_dir = _STATIC_DIR / "assets"
        if _assets_dir.exists():
            app.mount("/admin/assets", StaticFiles(directory=str(_assets_dir)), name="admin_assets")

        @app.get("/admin")
        @app.get("/admin/")
        async def admin_spa_root():
            return FileResponse(str(_index_path), media_type="text/html")

        @app.get("/admin/{path:path}")
        async def admin_spa_catchall(path: str):
            # /admin/assets/* is handled by the mount above; everything else is SPA client routing
            return FileResponse(str(_index_path), media_type="text/html")
