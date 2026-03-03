"""Configuration from environment."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root so BLUESKY_HANDLE / BLUESKY_APP_PASSWORD work without exporting
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# Database
DATABASE_PATH = Path(
    os.environ.get("DATABASE_PATH", str(Path(__file__).resolve().parent.parent.parent / "data" / "psu_feed.db"))
)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Jetstream
JETSTREAM_WS_URL = os.environ.get(
    "JETSTREAM_WS_URL",
    "wss://jetstream2.us-east.bsky.network/subscribe",
)

# Feed generator (for publish script and DID)
BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")
FEED_SERVICE_DID = os.environ.get("FEED_SERVICE_DID", "did:web:localhost")  # did:web:yourdomain.com in production
FEED_DISPLAY_NAME = os.environ.get("FEED_DISPLAY_NAME", "Blue and White Sky")
FEED_DESCRIPTION = os.environ.get(
    "FEED_DESCRIPTION",
    "Penn State football and other PSU coverage.",
)
FEED_RKEY = os.environ.get("FEED_RKEY", "psu-football")

# Authority: DIDs with 2.0x multiplier (managed via settings.json / admin UI)
from .settings import get_authority_dids as _get_settings_authority_dids  # noqa: E402
_env_authority_dids = os.environ.get("AUTHORITY_DIDS", "").strip()
_EXTRA_AUTHORITY_DIDS = {d.strip() for d in _env_authority_dids.split(",") if d.strip()} if _env_authority_dids else set()


def get_authority_dids() -> set[str]:
    """Current authority DIDs from settings plus any from AUTHORITY_DIDS env."""
    return _get_settings_authority_dids() | _EXTRA_AUTHORITY_DIDS

# HN ranking
GRAVITY = float(os.environ.get("PSU_FEED_GRAVITY", "1.5"))
POSTS_LOOKBACK_HOURS = int(os.environ.get("PSU_FEED_LOOKBACK_HOURS", "48"))
FEED_LIMIT = 50
# Authority posts without PSU keywords get mult *= this (so they rank lower; default 0.25 = 1/4)
AUTHORITY_OFFTOPIC_PENALTY = float(os.environ.get("PSU_FEED_AUTHORITY_OFFTOPIC_PENALTY", "0.25"))
