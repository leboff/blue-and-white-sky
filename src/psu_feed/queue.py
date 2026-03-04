"""Redis-backed task queues for classification and engagement. ARQ worker settings."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis

from .config import QUEUE_NAME_CLASSIFY, QUEUE_NAME_ENGAGEMENT, REDIS_URL

logger = logging.getLogger(__name__)


async def get_redis() -> redis.Redis:
    """Return an async Redis connection (caller should close or use as context manager)."""
    return redis.from_url(REDIS_URL, decode_responses=True)


async def enqueue_classify(payload: dict[str, Any]) -> None:
    """Push a classify job to the queue. payload: {uri, text, quoted_post_uri?}."""
    r = await get_redis()
    try:
        await r.lpush(QUEUE_NAME_CLASSIFY, json.dumps(payload, ensure_ascii=False))
    finally:
        await r.aclose()


async def enqueue_engagement(kind: str, subject_uri: str) -> None:
    """Push an engagement job. kind: 'like' | 'repost' | 'reply'."""
    r = await get_redis()
    try:
        await r.lpush(QUEUE_NAME_ENGAGEMENT, json.dumps({"kind": kind, "subject_uri": subject_uri}))
    finally:
        await r.aclose()


async def pop_classify_batch(max_size: int = 50) -> list[dict[str, Any]]:
    """Pop up to max_size classify jobs from the queue (batch for worker)."""
    r = await get_redis()
    try:
        batch = []
        for _ in range(max_size):
            raw = await r.rpop(QUEUE_NAME_CLASSIFY)
            if raw is None:
                break
            try:
                batch.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("invalid classify job: %r", raw[:200])
        return batch
    finally:
        await r.aclose()


async def pop_engagement_batch(max_size: int = 200) -> list[dict[str, Any]]:
    """Pop up to max_size engagement jobs from the queue."""
    r = await get_redis()
    try:
        batch = []
        for _ in range(max_size):
            raw = await r.rpop(QUEUE_NAME_ENGAGEMENT)
            if raw is None:
                break
            try:
                batch.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("invalid engagement job: %r", raw[:200])
        return batch
    finally:
        await r.aclose()
