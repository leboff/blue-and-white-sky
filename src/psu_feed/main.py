"""FastAPI app: describeFeedGenerator and getFeedSkeleton (HN-ranked)."""

from __future__ import annotations

import html
import httpx
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

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
from .ranking import calculate_hn_score, effective_authority_multiplier

app = FastAPI(title="Penn State Football Feed")

BSKY_GET_POSTS_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts"
GET_POSTS_BATCH = 25


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
        (
            uri,
            calculate_hn_score(
                likes,
                reposts,
                effective_authority_multiplier(mult, followers, keyword_matched),
                created_at,
                GRAVITY,
            ),
        )
        for uri, likes, reposts, mult, followers, keyword_matched, created_at in rows
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


async def _get_ranked_skeleton(
    limit: int,
    lookback_hours: int,
    gravity: float,
) -> list[tuple[str, float]]:
    """Return [(uri, score), ...] for the top ranked posts."""
    conn = await get_connection()
    try:
        rows = await get_recent_posts_with_authority(conn, lookback_hours)
    finally:
        await conn.close()
    scored = [
        (
            uri,
            calculate_hn_score(
                likes,
                reposts,
                effective_authority_multiplier(mult, followers, keyword_matched),
                created_at,
                gravity,
            ),
        )
        for uri, likes, reposts, mult, followers, keyword_matched, created_at in rows
    ]
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


async def _get_ranked_skeleton_with_meta(
    limit: int,
    lookback_hours: int,
    gravity: float,
) -> list[tuple[str, float, float, int | None, str]]:
    """Return [(uri, score, effective_authority_multiplier, followers_count, created_at), ...] for dev view."""
    conn = await get_connection()
    try:
        rows = await get_recent_posts_with_authority(conn, lookback_hours)
    finally:
        await conn.close()
    scored = [
        (
            uri,
            calculate_hn_score(
                likes,
                reposts,
                effective_authority_multiplier(mult, followers, keyword_matched),
                created_at,
                gravity,
            ),
            effective_authority_multiplier(mult, followers, keyword_matched),
            followers,
            created_at,
        )
        for uri, likes, reposts, mult, followers, keyword_matched, created_at in rows
    ]
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


async def _hydrate_posts(uris: list[str]) -> dict[str, dict]:
    """Fetch post views from Bluesky public API. Returns {uri: post_view_dict}."""
    out: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for i in range(0, len(uris), GET_POSTS_BATCH):
            batch = uris[i : i + GET_POSTS_BATCH]
            params = [("uris", u) for u in batch]
            r = await client.get(BSKY_GET_POSTS_URL, params=params)
            if r.status_code != 200:
                continue
            data = r.json()
            for post in data.get("posts") or []:
                uri = post.get("uri")
                if uri:
                    out[uri] = post
    return out


@app.get("/dev/feed")
async def dev_feed(
    limit: int = Query(20, ge=1, le=50),
    gravity: float = Query(None, description="HN gravity (default from config)"),
    lookback_hours: int = Query(None, description="Lookback hours (default from config)"),
):
    """
    Preview the feed with real post content. Use this to see what the feed returns
    and to tune gravity / lookback. Open in a browser: http://localhost:8000/dev/feed
    """
    g = gravity if gravity is not None else GRAVITY
    lookback = lookback_hours if lookback_hours is not None else POSTS_LOOKBACK_HOURS
    ranked = await _get_ranked_skeleton_with_meta(limit=limit, lookback_hours=lookback, gravity=g)
    if not ranked:
        html_body = "<p>No posts in the feed yet. Run the ingester and/or backfill to seed the DB.</p>"
    else:
        uris = [r[0] for r in ranked]
        hydrated = await _hydrate_posts(uris)
        # Compute live score (Bluesky API engagement) for each so order and displayed score are correct
        with_scores = []
        for uri, _db_score, mult, followers, created_at in ranked:
            post = hydrated.get(uri) or {}
            author = post.get("author") or {}
            handle = author.get("handle") or "?"
            display_name = author.get("displayName") or handle
            record = post.get("record") or {}
            text = record.get("text") or "(unable to load)"
            created = record.get("createdAt") or ""
            like_count = post.get("likeCount") or 0
            repost_count = post.get("repostCount") or 0
            score = calculate_hn_score(like_count, repost_count, mult, created_at, g)
            with_scores.append((score, uri, handle, display_name, text, like_count, repost_count, created))
        with_scores.sort(key=lambda x: -x[0])
        rows = []
        for i, (score, uri, handle, display_name, text, like_count, repost_count, created) in enumerate(with_scores, 1):
            rows.append(
                f"""
                <tr>
                    <td>{i}</td>
                    <td><strong>{html.escape(display_name)}</strong> @{html.escape(handle)}</td>
                    <td>{html.escape(text[:200])}{"…" if len(text) > 200 else ""}</td>
                    <td>{like_count} / {repost_count}</td>
                    <td>{score:.4f}</td>
                    <td>{html.escape(created[:19]) if created else ""}</td>
                    <td><a href="https://bsky.app/profile/{handle}/post/{uri.split('/')[-1]}" target="_blank">Open</a></td>
                </tr>
                """
            )
        html_body = f"""
        <p>Tuning: <a href="?limit={limit}&gravity=1.5&lookback_hours={lookback}">gravity=1.5</a> |
        <a href="?limit={limit}&gravity=1.8&lookback_hours={lookback}">1.8</a> |
        <a href="?limit={limit}&gravity={g}&lookback_hours=24">lookback=24h</a> |
        <a href="?limit={limit}&gravity={g}&lookback_hours=48">48h</a> |
        <a href="?limit={limit}&gravity={g}&lookback_hours=72">72h</a></p>
        <table border="1" cellpadding="8" style="border-collapse: collapse; width:100%;">
            <thead><tr>
                <th>#</th><th>Author</th><th>Text</th><th>Likes / Reposts</th><th>Score</th><th>Created</th><th>Link</th>
            </tr></thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
        """
    full = f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><title>PSU Feed Preview</title></head>
    <body>
        <h1>Penn State Feed — Preview</h1>
        {html_body}
    </body></html>
    """
    return HTMLResponse(full)
