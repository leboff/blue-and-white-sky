"""Bluesky ATproto feed routes: describeFeedGenerator, getFeedSkeleton, did.json."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..config import (
    FEED_DESCRIPTION,
    FEED_DISPLAY_NAME,
    FEED_LIMIT,
    FEED_RKEY,
    FEED_SERVICE_DID,
    POSTS_LOOKBACK_HOURS,
)
from ..services.skeleton import get_chronological_skeleton

router = APIRouter()


@router.get("/.well-known/did.json")
async def well_known_did(request: Request):
    """Serve did:web DID document so Bluesky can resolve FEED_SERVICE_DID to this server."""
    base = str(request.base_url).rstrip("/")
    return JSONResponse(
        content={
            "id": FEED_SERVICE_DID,
            "service": [
                {
                    "id": "#bsky_fg",
                    "type": "BskyFeedGenerator",
                    "serviceEndpoint": base,
                }
            ],
        }
    )


@router.get("/xrpc/app.bsky.feed.describeFeedGenerator")
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


@router.get("/xrpc/app.bsky.feed.getFeedSkeleton")
async def get_feed_skeleton(
    feed: str = Query(..., description="AT URI of the feed generator"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
):
    """
    Return a list of post URIs (skeleton). Bluesky hydrates them.
    Returns posts in purely chronological order.
    """
    limit = min(limit, FEED_LIMIT)
    scored = await get_chronological_skeleton(
        limit=limit,
        lookback_hours=POSTS_LOOKBACK_HOURS,
        cursor=cursor,
    )
    feed_list = [{"post": uri} for uri, _ in scored]

    next_cursor = None
    if len(scored) >= limit and scored:
        next_cursor = scored[-1][0]

    return JSONResponse(
        content={
            "feed": feed_list,
            **({"cursor": next_cursor} if next_cursor else {}),
        }
    )
