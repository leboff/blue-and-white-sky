"""Engagement worker: pop like/repost/reply jobs from Redis, update DB counts."""

from __future__ import annotations

import asyncio
import logging

from psu_feed.db import get_session, increment_likes, increment_replies, increment_reposts
from psu_feed.queue import pop_engagement_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 200
POLL_INTERVAL_SEC = 2


async def _run_once() -> None:
    jobs = await pop_engagement_batch(max_size=BATCH_SIZE)
    if not jobs:
        return
    async with get_session() as session:
        for j in jobs:
            kind = j.get("kind") or ""
            uri = j.get("subject_uri") or ""
            if not uri:
                continue
            if kind == "like":
                await increment_likes(session, uri)
            elif kind == "repost":
                await increment_reposts(session, uri)
            elif kind == "reply":
                await increment_replies(session, uri)
        logger.debug("applied %d engagement events", len(jobs))


async def run() -> None:
    while True:
        try:
            await _run_once()
        except Exception as e:
            logger.exception("engagement_worker error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_SEC)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
