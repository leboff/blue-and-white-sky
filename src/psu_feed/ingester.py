"""Jetstream WebSocket ingester: filter posts, track engagement, update user authority."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import websockets
from aiosqlite import Connection as SQLiteConnection

from .config import AUTHORITY_DIDS, JETSTREAM_WS_URL
from .db import (
    get_connection,
    init_db,
    increment_likes,
    increment_reposts,
    insert_post,
    maybe_promote_authority,
    upsert_user_authority,
    increment_user_match_count,
)
from .filter import is_relevant_post

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Collections we subscribe to
WANTED_COLLECTIONS = [
    "app.bsky.feed.post",
    "app.bsky.feed.like",
    "app.bsky.feed.repost",
]

AUTHORITY_THRESHOLD = 10
AUTHORITY_MULTIPLIER = 1.5
HARDCODED_AUTHORITY = 2.0


def _parse_created_at(record: dict) -> datetime | None:
    raw = record.get("createdAt")
    if not raw:
        return None
    try:
        # ISO format with optional Z
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _text_from_post_record(record: dict) -> str:
    """Extract plain text from a feed post record (supports facets but we only need text)."""
    return (record.get("text") or "").strip()


def _build_post_uri(did: str, path: str) -> str:
    """Build at:// URI from DID and path (e.g. app.bsky.feed.post/3jz...)."""
    return f"at://{did}/{path}"


async def _handle_post_create(conn: SQLiteConnection, did: str, commit: dict) -> None:
    record = commit.get("record") or {}
    path = commit.get("path") or ""
    if not path.startswith("app.bsky.feed.post/"):
        return
    text = _text_from_post_record(record)
    keyword_matched = 1 if is_relevant_post(text) else 0
    # Authority DIDs: include all posts (keyword_matched=0 when no PSU keywords). Others: only when keywords match.
    if did not in AUTHORITY_DIDS and not keyword_matched:
        return
    uri = _build_post_uri(did, path)
    created_at = _parse_created_at(record) or datetime.now(timezone.utc)
    cid = commit.get("cid") or ""
    await insert_post(conn, uri, cid, did, created_at, keyword_matched=keyword_matched)
    if did in AUTHORITY_DIDS:
        await upsert_user_authority(conn, did, HARDCODED_AUTHORITY)
    else:
        await increment_user_match_count(conn, did)
        await maybe_promote_authority(conn, did, AUTHORITY_THRESHOLD, AUTHORITY_MULTIPLIER)
    logger.info("indexed post did=%s uri=%s", did[:20], uri[:60])


def _subject_uri_from_record(record: dict) -> str | None:
    """Get subject URI from a like or repost record."""
    subject = record.get("subject")
    if isinstance(subject, str):
        return subject
    if isinstance(subject, dict) and "uri" in subject:
        return subject["uri"]
    return None


async def _handle_like_create(conn: SQLiteConnection, commit: dict) -> None:
    record = commit.get("record") or {}
    uri = _subject_uri_from_record(record)
    if not uri:
        return
    await increment_likes(conn, uri)
    logger.debug("like subject=%s", uri[:60])


async def _handle_repost_create(conn: SQLiteConnection, commit: dict) -> None:
    record = commit.get("record") or {}
    uri = _subject_uri_from_record(record)
    if not uri:
        return
    await increment_reposts(conn, uri)
    logger.debug("repost subject=%s", uri[:60])


async def _process_message(conn: SQLiteConnection, raw: str) -> None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    if data.get("kind") != "commit":
        return
    commit = data.get("commit") or {}
    did = data.get("did") or ""
    operation = commit.get("operation") or ""
    collection = commit.get("collection") or ""
    if operation != "create":
        return
    if collection == "app.bsky.feed.post":
        await _handle_post_create(conn, did, commit)
    elif collection == "app.bsky.feed.like":
        await _handle_like_create(conn, commit)
    elif collection == "app.bsky.feed.repost":
        await _handle_repost_create(conn, commit)


async def run_ingester() -> None:
    await init_db()
    url = JETSTREAM_WS_URL
    params = "&".join(f"wantedCollections={c}" for c in WANTED_COLLECTIONS)
    if "?" in url:
        full_url = f"{url}&{params}"
    else:
        full_url = f"{url}?{params}"
    logger.info("connecting to %s", full_url.split("?")[0])
    while True:
        try:
            async with websockets.connect(
                full_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                conn = await get_connection()
                try:
                    async for message in ws:
                        await _process_message(conn, message)
                        await conn.commit()
                finally:
                    await conn.close()
        except websockets.ConnectionClosed as e:
            logger.warning("connection closed: %s", e)
        except Exception as e:
            logger.exception("ingester error: %s", e)
        await asyncio.sleep(5)


def main() -> None:
    asyncio.run(run_ingester())


if __name__ == "__main__":
    main()
