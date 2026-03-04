"""Dev API: feed preview and classify/delete (JSON only)."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query

from ..classifier import classify_posts as llm_classify_posts
from ..config import GRAVITY, POSTS_LOOKBACK_HOURS
from ..db import delete_post, get_session, update_post_classification
from ..ranking import calculate_hn_score
from ..services.skeleton import (
    get_ranked_skeleton_with_meta,
    hydrate_posts,
    llm_status_label,
    quoted_text_from_hydrated_post,
)

router = APIRouter()


@router.get("/dev/feed")
async def dev_feed(
    limit: int = Query(20, ge=1, le=50),
    gravity: float = Query(None, description="HN gravity (default from config)"),
    lookback_hours: int = Query(None, description="Lookback hours (default from config)"),
    show_all: bool = Query(False, description="Include pending and rejected posts"),
):
    """
    Preview the feed with real post content (JSON). Returns list of posts with score, author, text, engagement, status.
    """
    g = gravity if gravity is not None else GRAVITY
    lookback = lookback_hours if lookback_hours is not None else POSTS_LOOKBACK_HOURS
    ranked = await get_ranked_skeleton_with_meta(
        limit=limit, lookback_hours=lookback, gravity=g, include_pending_rejected=show_all
    )
    if not ranked:
        return {"posts": [], "message": "No posts in the feed yet. Run the ingester and/or backfill to seed the DB."}

    uris = [r[0] for r in ranked]
    hydrated = await hydrate_posts(uris)

    with_scores = []
    for uri, _db_score, mult, followers, created_at, author_did, llm_approved in ranked:
        post = hydrated.get(uri) or {}
        author = post.get("author") or {}
        handle = author.get("handle") or "?"
        display_name = author.get("displayName") or handle
        record = post.get("record") or {}
        text = record.get("text") or "(unable to load)"
        created = record.get("createdAt") or ""
        like_count = post.get("likeCount") or 0
        repost_count = post.get("repostCount") or 0
        reply_count = post.get("replyCount") or 0
        embed = record.get("embed")
        has_media = 0
        if isinstance(embed, dict):
            embed_type = embed.get("$type")
            if embed_type in ("app.bsky.embed.images", "app.bsky.embed.video", "app.bsky.embed.external", "app.bsky.embed.recordWithMedia"):
                has_media = 1

        quoted_text = quoted_text_from_hydrated_post(post)
        score = calculate_hn_score(like_count, repost_count, reply_count, has_media, mult, created_at, g)
        status = llm_status_label(llm_approved)
        link = f"https://bsky.app/profile/{handle}/post/{uri.split('/')[-1]}" if handle else ""
        with_scores.append({
            "uri": uri,
            "score": round(score, 4),
            "handle": handle,
            "display_name": display_name,
            "text": text,
            "like_count": like_count,
            "repost_count": repost_count,
            "reply_count": reply_count,
            "created": created,
            "llm_status": status,
            "quoted_text": quoted_text,
            "link": link,
        })

    with_scores.sort(key=lambda x: -x["score"])
    return {"posts": with_scores}


@router.post("/dev/feed/delete-post")
async def dev_feed_delete_post(body: dict = Body(...)):
    """Delete a post from the DB by URI (for dev feed cleanup)."""
    uri = body.get("uri")
    if not uri or not isinstance(uri, str):
        raise HTTPException(400, "body must include uri (string)")
    async with get_session() as session:
        deleted = await delete_post(session, uri.strip())
    if not deleted:
        raise HTTPException(404, "post not found")
    return {"ok": True}


@router.post("/dev/feed/classify-post")
async def dev_feed_classify_post(body: dict = Body(...)):
    """Run LLM classification for a single post. Body: {uri, text, optional quoted_text}. Returns {ok: true, relevant: bool}."""
    uri = body.get("uri")
    text = body.get("text")
    quoted_text = body.get("quoted_text")
    if not uri or not isinstance(uri, str):
        raise HTTPException(400, "body must include uri (string)")
    if text is None:
        text = ""
    text = str(text)
    quoted_text = (str(quoted_text) if quoted_text is not None else "").strip() or None
    payload: dict = {"id": uri.strip(), "post": text}
    if quoted_text:
        payload["quoted_post"] = quoted_text
    try:
        result = await llm_classify_posts([payload])
    except ValueError as e:
        raise HTTPException(503, str(e))
    relevant = result.get(uri.strip(), False)
    async with get_session() as session:
        await update_post_classification(session, [(uri.strip(), 1 if relevant else 2)])
    return {"ok": True, "relevant": relevant}
