"""Feed skeleton ranking and post hydration. Used by feed and dev API routes."""

from __future__ import annotations

import httpx

from ..db import get_recent_posts_with_authority, get_session
from ..ranking import calculate_hn_score, effective_authority_multiplier

BSKY_GET_POSTS_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts"
GET_POSTS_BATCH = 25


async def get_ranked_skeleton(
    limit: int,
    lookback_hours: int,
    gravity: float,
) -> list[tuple[str, float]]:
    """Return [(uri, score), ...] for the top ranked posts."""
    async with get_session() as session:
        rows = await get_recent_posts_with_authority(session, lookback_hours)

    scored_initial = []
    for row in rows:
        base_score = calculate_hn_score(
            row.likes_count,
            row.reposts_count,
            row.replies_count,
            row.has_media,
            effective_authority_multiplier(row.authority_multiplier, row.followers_count, row.keyword_matched),
            row.created_at,
            gravity,
        )
        scored_initial.append((row.uri, base_score, row.author_did))

    scored_initial.sort(key=lambda x: -x[1])

    author_counts: dict[str, int] = {}
    scored = []
    for uri, score, author_did in scored_initial:
        count = author_counts.get(author_did, 0)
        diversity_penalty = 0.8 ** count
        final_score = score * diversity_penalty
        author_counts[author_did] = count + 1
        scored.append((uri, final_score))

    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


async def get_ranked_skeleton_with_meta(
    limit: int,
    lookback_hours: int,
    gravity: float,
    include_pending_rejected: bool = False,
) -> list[tuple[str, float, float, int | None, str, str, int]]:
    """Return [(uri, score, eff_mult, followers, created_at, author_did, llm_approved), ...]. llm_approved: 0=pending, 1=approved, 2=rejected."""
    async with get_session() as session:
        rows = await get_recent_posts_with_authority(
            session, lookback_hours, include_pending_rejected=include_pending_rejected
        )

    scored_initial = []
    for row in rows:
        base_score = calculate_hn_score(
            row.likes_count,
            row.reposts_count,
            row.replies_count,
            row.has_media,
            effective_authority_multiplier(row.authority_multiplier, row.followers_count, row.keyword_matched),
            row.created_at,
            gravity,
        )
        eff_mult = effective_authority_multiplier(row.authority_multiplier, row.followers_count, row.keyword_matched)
        scored_initial.append((row.uri, base_score, eff_mult, row.followers_count, row.created_at, row.author_did, row.llm_approved))

    scored_initial.sort(key=lambda x: -x[1])

    author_counts: dict[str, int] = {}
    scored = []
    for item in scored_initial:
        uri, score, eff_mult, followers, created_at, author_did, llm_approved = item
        count = author_counts.get(author_did, 0)
        diversity_penalty = 0.8 ** count
        final_score = score * diversity_penalty
        author_counts[author_did] = count + 1
        scored.append((uri, final_score, eff_mult, followers, created_at, author_did, llm_approved))

    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


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
