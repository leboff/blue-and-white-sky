"""Redis-backed task queues for classification and engagement. Uses a shared pool to avoid connection churn."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from .config import (
    QUEUE_MAX_LEN_CLASSIFY,
    QUEUE_MAX_LEN_ENGAGEMENT,
    QUEUE_NAME_CLASSIFY,
    QUEUE_NAME_ENGAGEMENT,
    REDIS_URL,
)

logger = logging.getLogger(__name__)

# Shared pool so we don't open a new TCP connection per enqueue (avoids "Cannot assign requested address")
_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            REDIS_URL,
            decode_responses=True,
            max_connections=10,
        )
    return _pool


def get_redis() -> redis.Redis:
    """Return a Redis client using the shared pool. Call await client.aclose() when done to return the connection to the pool."""
    return redis.Redis(connection_pool=_get_pool())


async def enqueue_classify(payload: dict[str, Any]) -> None:
    """Push a classify job to the queue. payload: {uri, text, quoted_post_uri?}. List is capped to QUEUE_MAX_LEN_CLASSIFY."""
    r = get_redis()
    try:
        await r.lpush(QUEUE_NAME_CLASSIFY, json.dumps(payload, ensure_ascii=False))
        await r.ltrim(QUEUE_NAME_CLASSIFY, 0, QUEUE_MAX_LEN_CLASSIFY - 1)
    finally:
        await r.aclose()


async def enqueue_engagement(kind: str, subject_uri: str) -> None:
    """Push an engagement job. kind: 'like' | 'repost' | 'reply'. List is capped to QUEUE_MAX_LEN_ENGAGEMENT."""
    r = get_redis()
    try:
        await r.lpush(QUEUE_NAME_ENGAGEMENT, json.dumps({"kind": kind, "subject_uri": subject_uri}))
        await r.ltrim(QUEUE_NAME_ENGAGEMENT, 0, QUEUE_MAX_LEN_ENGAGEMENT - 1)
    finally:
        await r.aclose()


async def pop_classify_batch(max_size: int = 50) -> list[dict[str, Any]]:
    """Pop up to max_size classify jobs from the queue (batch for worker)."""
    r = get_redis()
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
    r = get_redis()
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
