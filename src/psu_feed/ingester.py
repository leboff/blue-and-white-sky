"""Jetstream WebSocket ingester: filter posts, track engagement, update user authority."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import websockets

from .config import get_authority_dids, JETSTREAM_WS_URL, require_bluesky_credentials
from .db import (
    get_session,
    init_db,
    insert_post,
    maybe_promote_authority,
    post_has_keyword_match,
    upsert_user_authority,
    increment_user_match_count,
)
from .filter import is_relevant_post
from .queue import enqueue_classify, enqueue_engagement
from . import settings as settings_module

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Expected for long-lived WS: server/network drops without close frame; we reconnect.
logging.getLogger("websockets").setLevel(logging.ERROR)

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


def _quoted_post_uri_from_record(record: dict) -> str | None:
    """Extract the quoted post URI from a post record (quote repost embed). Returns None if not a quote."""
    embed = record.get("embed")
    if not isinstance(embed, dict):
        return None
    # app.bsky.embed.record: { "record": { "uri": "at://...", "cid": "..." } }
    rec = embed.get("record")
    if isinstance(rec, dict) and rec.get("uri"):
        return (rec.get("uri") or "").strip() or None
    # app.bsky.embed.recordWithMedia: { "record": { "record": { "uri": "...", "cid": "..." } }, "media": ... }
    if isinstance(rec, dict):
        inner = rec.get("record")
        if isinstance(inner, dict) and inner.get("uri"):
            return (inner.get("uri") or "").strip() or None
    return None


def _build_post_uri(did: str, path: str) -> str:
    """Build at:// URI from DID and path (e.g. app.bsky.feed.post/3jz...)."""
    return f"at://{did}/{path}"


async def _handle_post_create(conn: SQLiteConnection, did: str, commit: dict) -> None:
    record = commit.get("record") or {}
    # Jetstream sends "path" (full path) or "collection" + "rkey"; build path if needed
    path = commit.get("path") or ""
    if not path.startswith("app.bsky.feed.post/"):
        coll = commit.get("collection") or ""
        rkey = commit.get("rkey") or ""
        if coll == "app.bsky.feed.post" and rkey:
            path = f"{coll}/{rkey}"
        else:
            return
    text = _text_from_post_record(record)
    keyword_matched = 1 if is_relevant_post(text) else 0
    # Include quote reposts when the quoted post is in our DB with keyword_matched=1
    if not keyword_matched:
        quoted_uri = _quoted_post_uri_from_record(record)
        if quoted_uri:
            async with get_session() as session:
                if await post_has_keyword_match(session, quoted_uri):
                    keyword_matched = 1
            
    reply = record.get("reply")
    if isinstance(reply, dict) and "parent" in reply:
        parent_uri = reply["parent"].get("uri")
        if parent_uri:
            try:
                await enqueue_engagement("reply", parent_uri)
            except Exception as e:
                logger.warning("enqueue_engagement reply failed: %s", e)

    embed = record.get("embed")
    has_media = 0
    if isinstance(embed, dict):
        embed_type = embed.get("$type")
        if embed_type in ("app.bsky.embed.images", "app.bsky.embed.video", "app.bsky.embed.external", "app.bsky.embed.recordWithMedia"):
            has_media = 1

    # Authority DIDs: include all posts (keyword_matched=0 when no PSU keywords). Others: only when keywords match (or quote of match).
    authority_dids = get_authority_dids()
    if did not in authority_dids and not keyword_matched:
        logger.debug("skipped post did=%s (not authority, no keyword match) text=%.80r", did[:20], (text or "")[:80])
        return
    uri = _build_post_uri(did, path)
    created_at = _parse_created_at(record) or datetime.now(timezone.utc)
    cid = commit.get("cid") or ""
    quoted_uri = _quoted_post_uri_from_record(record)
    # Live stream: insert as pending (llm_approved=0) and store text + quoted_uri for batch classification
    async with get_session() as session:
        await insert_post(
            session, uri, cid, did, created_at,
            keyword_matched=keyword_matched, has_media=has_media,
            llm_approved=0, post_text=text or None, quoted_post_uri=quoted_uri,
        )
        if did in authority_dids:
            await upsert_user_authority(session, did, HARDCODED_AUTHORITY)
        else:
            await increment_user_match_count(session, did)
            await maybe_promote_authority(session, did, AUTHORITY_THRESHOLD, AUTHORITY_MULTIPLIER)
    try:
        await enqueue_classify({"uri": uri, "text": text or "", "quoted_post_uri": quoted_uri})
    except Exception as e:
        logger.warning("enqueue_classify failed: %s", e)
    logger.info("indexed post did=%s uri=%s", did[:20], uri[:60])


def _subject_uri_from_record(record: dict) -> str | None:
    """Get subject URI from a like or repost record."""
    subject = record.get("subject")
    if isinstance(subject, str):
        return subject
    if isinstance(subject, dict) and "uri" in subject:
        return subject["uri"]
    return None


async def _handle_like_create(commit: dict) -> None:
    record = commit.get("record") or {}
    uri = _subject_uri_from_record(record)
    if not uri:
        return
    try:
        await enqueue_engagement("like", uri)
    except Exception as e:
        logger.warning("enqueue_engagement like failed: %s", e)
    logger.debug("like subject=%s", uri[:60])


async def _handle_repost_create(conn: SQLiteConnection, commit: dict) -> None:
    record = commit.get("record") or {}
    uri = _subject_uri_from_record(record)
    if not uri:
        return
    try:
        await enqueue_engagement("repost", uri)
    except Exception as e:
        logger.warning("enqueue_engagement repost failed: %s", e)
    logger.debug("repost subject=%s", uri[:60])


async def _reload_settings_loop() -> None:
    """Every 60s re-read settings file so UI edits are picked up without restart."""
    while True:
        await asyncio.sleep(60)
        settings_module.reload_if_changed()


async def _process_message(raw: str) -> None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    # Accept messages with kind=="commit" or any message that has commit+did (some streams omit "kind")
    if data.get("kind") != "commit" and not (data.get("commit") and data.get("did")):
        return
    commit = data.get("commit") or {}
    did = data.get("did") or ""
    operation = commit.get("operation") or ""
    collection = commit.get("collection") or ""
    if operation != "create":
        return
    if collection == "app.bsky.feed.post":
        await _handle_post_create(did, commit)
    elif collection == "app.bsky.feed.like":
        await _handle_like_create(commit)
    elif collection == "app.bsky.feed.repost":
        await _handle_repost_create(commit)


async def run_ingester() -> None:
    require_bluesky_credentials()
    await init_db()
    url = JETSTREAM_WS_URL
    params = "&".join(f"wantedCollections={c}" for c in WANTED_COLLECTIONS)
    if "?" in url:
        full_url = f"{url}&{params}"
    else:
        full_url = f"{url}?{params}"
    authority_count = len(get_authority_dids())
    keyword_count = len(settings_module.get_keywords())
    logger.info(
        "ingester starting: %d authority DIDs, %d keywords (connect to %s)",
        authority_count,
        keyword_count,
        full_url.split("?")[0],
    )
    if authority_count == 0 and keyword_count == 0:
        logger.warning("no authorities and no keywords loaded — no posts will be indexed until settings are configured")
    while True:
        try:
            settings_module.reload_if_changed()
            async with websockets.connect(
                full_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                reload_task = asyncio.create_task(_reload_settings_loop())

                try:
                    async for message in ws:
                        await _process_message(message)
                finally:
                    reload_task.cancel()
                    try:
                        await reload_task
                    except asyncio.CancelledError:
                        pass
        except websockets.ConnectionClosed as e:
            # Normal for long-lived connections: server/network may drop without close frame
            logger.info("connection closed (%s), reconnecting in 5s", e)
        except Exception as e:
            logger.exception("ingester error: %s", e)
        await asyncio.sleep(5)


def main() -> None:
    asyncio.run(run_ingester())


if __name__ == "__main__":
    main()
