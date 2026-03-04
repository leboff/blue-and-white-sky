import os
from pathlib import Path
from dotenv import load_dotenv

# 1. Load .env if it exists. 
# In Dokploy/Docker, variables are usually injected directly into the shell, 
# so we don't need a strict path. This will look in the current working directory.
load_dotenv()

# Base Directory for relative paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# --- Database ---
# Prefer setting DATABASE_PATH explicitly via environment. If missing, default to /app/data/psu_feed.db for Docker,
# or fallback to local ./data/psu_feed.db
_default_db_dir = Path("/app/data") if Path("/app").exists() else (BASE_DIR / "data")
DATABASE_PATH = Path(
    os.environ.get("DATABASE_PATH", str(_default_db_dir / "psu_feed.db"))
)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# --- Jetstream ---
JETSTREAM_WS_URL = os.environ.get(
    "JETSTREAM_WS_URL",
    "wss://jetstream2.us-east.bsky.network/subscribe",
)

# --- Feed Generator (Required for API / ingester) ---
BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "").strip()
BLUESKY_APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "").strip()

def require_bluesky_credentials() -> None:
    """Call from API or ingester entrypoints. Raises if credentials are missing."""
    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        raise EnvironmentError(
            "Missing BLUESKY_HANDLE or BLUESKY_APP_PASSWORD in environment variables. "
            "Check your Dokploy environment configuration."
        )

# --- Feed Identity & Metadata ---
# did:web:yourdomain.com in production
FEED_SERVICE_DID = os.environ.get("FEED_SERVICE_DID", "did:web:localhost")
FEED_DISPLAY_NAME = os.environ.get("FEED_DISPLAY_NAME", "Blue and White Sky")
FEED_DESCRIPTION = os.environ.get(
    "FEED_DESCRIPTION",
    "Penn State football and other PSU coverage. Work in progress.",
)
FEED_RKEY = os.environ.get("FEED_RKEY", "blue-and-white-sky")

# --- Authority & Ranking ---
from .settings import get_authority_dids as _get_settings_authority_dids

_env_authority_dids = os.environ.get("AUTHORITY_DIDS", "").strip()
_EXTRA_AUTHORITY_DIDS = {
    d.strip() for d in _env_authority_dids.split(",") if d.strip()
} if _env_authority_dids else set()

def get_authority_dids() -> set[str]:
    """Current authority DIDs from settings plus any from AUTHORITY_DIDS env."""
    return _get_settings_authority_dids() | _EXTRA_AUTHORITY_DIDS

# HN ranking parameters
GRAVITY = float(os.environ.get("PSU_FEED_GRAVITY", "1.5"))
POSTS_LOOKBACK_HOURS = int(os.environ.get("PSU_FEED_LOOKBACK_HOURS", "48"))
FEED_LIMIT = 50

# Authority posts without PSU keywords get rank penalty (default 0.25)
AUTHORITY_OFFTOPIC_PENALTY = float(os.environ.get("PSU_FEED_AUTHORITY_OFFTOPIC_PENALTY", "0.25"))

# Minimum numerator for HN score so new posts with no engagement still appear (default 1.0). They decay with age.
FRESH_POST_SCORE_FLOOR = float(os.environ.get("PSU_FEED_FRESH_POST_SCORE_FLOOR", "1.0"))

# --- Redis / Task queue (ARQ) ---
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
QUEUE_NAME_CLASSIFY = "psu_feed:classify"
QUEUE_NAME_ENGAGEMENT = "psu_feed:engagement"
