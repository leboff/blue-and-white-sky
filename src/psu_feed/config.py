"""Configuration from environment."""

import os
from pathlib import Path

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
FEED_DISPLAY_NAME = os.environ.get("FEED_DISPLAY_NAME", "Penn State Football")
FEED_DESCRIPTION = os.environ.get(
    "FEED_DESCRIPTION",
    "Penn State football: Nittany Lions, Beaver Stadium, and PSU coverage.",
)
FEED_RKEY = os.environ.get("FEED_RKEY", "psu-football")

# Authority: DIDs that get a fixed 2.0 multiplier (beat reporters / official accounts)
AUTHORITY_DIDS: set[str] = set(
    os.environ.get("AUTHORITY_DIDS", "").split(",") if os.environ.get("AUTHORITY_DIDS") else []
)

# HN ranking
GRAVITY = float(os.environ.get("PSU_FEED_GRAVITY", "1.5"))
POSTS_LOOKBACK_HOURS = int(os.environ.get("PSU_FEED_LOOKBACK_HOURS", "48"))
FEED_LIMIT = 50
