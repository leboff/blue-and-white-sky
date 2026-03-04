"""Classifier worker: pop classify jobs from Redis, run LLM, update DB."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from psu_feed.classifier import classify_posts as llm_classify_posts
from psu_feed.db import get_session, update_post_classification
from psu_feed.queue import pop_classify_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BSKY_GET_POSTS_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts"
BATCH_SIZE = 50
POLL_INTERVAL_SEC = 10


async def _fetch_post_texts(uris: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for i in range(0, len(uris), 25):
            batch = uris[i : i + 25]
            params = [("uris", u) for u in batch]
            try:
                r = await client.get(BSKY_GET_POSTS_URL, params=params)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            data = r.json()
            for post in data.get("posts") or []:
                uri = post.get("uri")
                if not uri:
                    continue
                record = post.get("record") or {}
                out[uri] = (record.get("text") or "").strip()
    return out


async def _run_once() -> None:
    jobs = await pop_classify_batch(max_size=BATCH_SIZE)
    if not jobs:
        return
    quoted_uris = [j.get("quoted_post_uri") for j in jobs if j.get("quoted_post_uri")]
    quoted_uris = list(dict.fromkeys(u for u in quoted_uris if u))
    quoted_texts = await _fetch_post_texts(quoted_uris) if quoted_uris else {}
    to_send = []
    for j in jobs:
        uri = j.get("uri") or ""
        text = (j.get("text") or "").strip()
        quoted_uri = j.get("quoted_post_uri")
        if not text and not quoted_texts.get(quoted_uri or ""):
            continue
        item: dict = {"id": uri, "post": text}
        if quoted_uri and quoted_texts.get(quoted_uri):
            item["quoted_post"] = quoted_texts[quoted_uri]
        to_send.append((uri, item))
    if not to_send:
        return
    uris_ordered = [u for u, _ in to_send]
    payloads = [item for _, item in to_send]
    try:
        result = await llm_classify_posts(payloads)
    except ValueError as e:
        logger.warning("LLM classification skipped: %s", e)
        return
    updates = [(uri, 1 if result.get(uri, False) else 2) for uri in uris_ordered]
    async with get_session() as session:
        await update_post_classification(session, updates)
        approved = sum(1 for _, v in updates if v == 1)
        logger.info("classified %d posts: %d approved, %d rejected", len(updates), approved, len(updates) - approved)


async def run() -> None:
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        logger.warning("GEMINI_API_KEY not set — classifier worker idle")
    while True:
        try:
            await _run_once()
        except Exception as e:
            logger.exception("classifier_worker error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_SEC)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
