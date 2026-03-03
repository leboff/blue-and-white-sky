"""FastAPI app: describeFeedGenerator and getFeedSkeleton (HN-ranked)."""

from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from .config import (
    FEED_DESCRIPTION,
    FEED_DISPLAY_NAME,
    FEED_LIMIT,
    FEED_RKEY,
    FEED_SERVICE_DID,
    GRAVITY,
    POSTS_LOOKBACK_HOURS,
)
from .db import get_connection, get_recent_posts_with_authority
from .ranking import calculate_hn_score

app = FastAPI(title="Penn State Football Feed")


@app.get("/xrpc/app.bsky.feed.describeFeedGenerator")
async def describe_feed_generator():
    """List this server's feed URIs (caller uses this to discover feeds)."""
    feed_uri = f"at://{FEED_SERVICE_DID}/app.bsky.feed.generator/{FEED_RKEY}"
    return {
        "encoding": "application/json",
        "body": {
            "did": FEED_SERVICE_DID,
            "feeds": [
                {
                    "uri": feed_uri,
                    "displayName": FEED_DISPLAY_NAME,
                    "description": FEED_DESCRIPTION,
                }
            ],
        },
    }


@app.get("/xrpc/app.bsky.feed.getFeedSkeleton")
async def get_feed_skeleton(
    feed: str = Query(..., description="AT URI of the feed generator"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
):
    """
    Return a ranked list of post URIs (skeleton). Bluesky hydrates them.
    Ranked by HN-style score: (engagement * authority - 1) / (age_hours + 2)^gravity.
    """
    limit = min(limit, FEED_LIMIT)
    conn = await get_connection()
    try:
        rows = await get_recent_posts_with_authority(conn, POSTS_LOOKBACK_HOURS)
    finally:
        await conn.close()

    scored = [
        (uri, calculate_hn_score(likes, reposts, mult, created_at, GRAVITY))
        for uri, likes, reposts, mult, created_at in rows
    ]
    scored.sort(key=lambda x: -x[1])
    top = scored[:limit]
    feed_list = [{"post": uri} for uri, _ in top]

    # Optional cursor for pagination (e.g. last post URI or timestamp)
    next_cursor = None
    if len(scored) > limit and top:
        next_cursor = top[-1][0]

    return JSONResponse(
        content={
            "feed": feed_list,
            **({"cursor": next_cursor} if next_cursor else {}),
        }
    )
