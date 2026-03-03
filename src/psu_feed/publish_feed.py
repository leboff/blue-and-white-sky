"""Publish the Penn State feed generator record to your Bluesky account."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from atproto import Client
from atproto_client.models.app.bsky.feed.generator import Record as GeneratorRecord
from atproto_client.models.com.atproto.repo.put_record import Data as PutRecordData

from .config import (
    BLUESKY_APP_PASSWORD,
    BLUESKY_HANDLE,
    FEED_DESCRIPTION,
    FEED_DISPLAY_NAME,
    FEED_RKEY,
    FEED_SERVICE_DID,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set this to the path of your avatar image (e.g., 'avatar.png' or 'avatar.jpg')
AVATAR_PATH = "avatar.png"


def main() -> None:
    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        logger.error("Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD in the environment (e.g. .env)")
        raise SystemExit(1)
    client = Client()
    client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
    repo = client.me.did
    rkey = FEED_RKEY

    avatar_blob = None
    avatar_file = Path(AVATAR_PATH)
    if avatar_file.exists():
        with open(avatar_file, "rb") as f:
            img_data = f.read()
            logger.info("Uploading avatar blob...")
            upload_resp = client.com.atproto.repo.upload_blob(img_data)
            avatar_blob = upload_resp.blob
    else:
        logger.warning("Avatar image not found at %s. Publishing without an icon.", AVATAR_PATH)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    record = GeneratorRecord(
        created_at=now,
        did=FEED_SERVICE_DID,
        display_name=FEED_DISPLAY_NAME,
        description=FEED_DESCRIPTION,
        avatar=avatar_blob,
    )
    data = PutRecordData(
        collection="app.bsky.feed.generator",
        record=record,
        repo=repo,
        rkey=rkey,
    )
    resp = client.com.atproto.repo.put_record(data)
    feed_uri = resp.uri
    logger.info("Published feed generator: %s", feed_uri)
    logger.info("Add this feed in the Bluesky app (Discover Feeds) using the above URI.")


if __name__ == "__main__":
    main()
