"""Feed skeleton ranking and post hydration. Used by feed and dev API routes."""

from __future__ import annotations

import httpx

from ..db import get_recent_posts_with_authority, get_session

BSKY_GET_POSTS_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts"
GET_POSTS_BATCH = 25


async def get_chronological_skeleton(
    limit: int,
    lookback_hours: int,
    cursor: str | None = None,
) -> list[tuple[str, float]]:
    """Return [(uri, score), ...] for the newest posts. If cursor is set, return posts older than that URI."""
    async with get_session() as session:
        rows = await get_recent_posts_with_authority(
            session, lookback_hours, cursor_uri=cursor, limit=limit
        )

    return [(row.uri, 0.0) for row in rows]


async def get_chronological_skeleton_with_meta(
    limit: int,
    lookback_hours: int,
    include_pending_rejected: bool = False,
) -> list[tuple[str, float, float, int | None, str, str, int]]:
    """Return [(uri, score, eff_mult, followers, created_at, author_did, llm_approved), ...]. llm_approved: 0=pending, 1=approved, 2=rejected."""
    async with get_session() as session:
        rows = await get_recent_posts_with_authority(
            session, lookback_hours, include_pending_rejected=include_pending_rejected
        )

    return [
        (row.uri, 0.0, 1.0, row.followers_count, row.created_at, row.author_did, row.llm_approved)
        for row in rows[:limit]
    ]


async def hydrate_posts(uris: list[str]) -> dict[str, dict]:
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


def quoted_text_from_hydrated_post(post: dict) -> str:
    """Extract quoted/reposted post text from a hydrated getPosts post dict."""
    record = post.get("record") or {}
    embed = record.get("embed") or post.get("embed")
    if not isinstance(embed, dict):
        return ""
    rec = embed.get("record")
    if not isinstance(rec, dict):
        return ""
    val = rec.get("value") or rec
    if isinstance(val, dict):
        return (val.get("text") or "").strip()
    return ""


def llm_status_label(llm_approved: int) -> str:
    """Return 'pending', 'approved', or 'rejected' for llm_approved 0, 1, 2."""
    if llm_approved == 0:
        return "pending"
    if llm_approved == 1:
        return "approved"
    return "rejected"
