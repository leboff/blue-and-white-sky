"""
Backfill the feed from historical data: authority accounts' posts and keyword search.

Run after setting BLUESKY_HANDLE and BLUESKY_APP_PASSWORD (same as publish).
  python -m psu_feed.backfill [--authority-only] [--search-only] [--since ISO] [--until ISO]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
from datetime import datetime, timezone

from atproto import Client
from atproto_client.models.app.bsky.feed.get_author_feed import Params as AuthorFeedParams
from atproto_client.models.app.bsky.feed.search_posts import Params as SearchPostsParams

from .authority_dids import get_authority_accounts, get_authority_dids
from .config import BLUESKY_APP_PASSWORD, BLUESKY_HANDLE, DATABASE_PATH
from .db import (
    get_keyword_matched_uris,
    get_session,
    init_db,
    insert_post,
    increment_user_match_count,
    maybe_promote_authority,
    update_user_followers,
    upsert_user_authority,
)
from .filter import is_relevant_post
from . import settings as settings_module

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Authority multiplier for listed accounts
HARDCODED_AUTHORITY = 2.0
AUTHORITY_THRESHOLD = 10
AUTHORITY_MULTIPLIER = 1.5


def _keyword_to_search_phrase(kw: str) -> str:
    """Turn a regex keyword into a plain search phrase for the search API."""
    s = kw
    s = re.sub(r"\\s\?", " ", s)
    s = re.sub(r"\\b", "", s)
    s = re.sub(r"\?$", "", s)  # trailing regex optional
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _get_search_queries() -> list[str]:
    """Search phrases derived from settings keywords (unique, non-empty, min 2 chars)."""
    keywords = settings_module.get_keywords()
    seen: set[str] = set()
    out: list[str] = []
    for kw in keywords:
        phrase = _keyword_to_search_phrase(kw)
        if len(phrase) >= 2 and phrase not in seen:
            seen.add(phrase)
            out.append(phrase)
    return out if out else ["Penn State", "Nittany Lions", "PSU football"]  # fallback if no keywords


def _record_dict(post) -> dict:
    """Get post record as a dict for consistent access (embed, text, etc.)."""
    record = getattr(post, "record", None)
    if record is None:
        return {}
    if callable(getattr(record, "get", None)):
        return record
    d = {}
    for k in ("text", "embed", "createdAt", "created_at"):
        v = getattr(record, k, None)
        if v is not None:
            d[k] = v
    return d


def _text_from_post(post) -> str:
    # PostView can have .text at top level or inside .record
    text = getattr(post, "text", None)
    if not text:
        record = _record_dict(post)
        text = record.get("text")
    return (text or "").strip()


def _get_embed_record_uri(embed) -> str | None:
    """Extract quoted record URI from an embed (dict or object)."""
    if embed is None:
        return None
    rec = embed.get("record") if isinstance(embed, dict) else getattr(embed, "record", None)
    if rec is None:
        return None
    uri = rec.get("uri") if isinstance(rec, dict) else getattr(rec, "uri", None)
    if uri:
        return (uri.strip() or None)
    inner = rec.get("record") if isinstance(rec, dict) else getattr(rec, "record", None)
    if isinstance(inner, dict) and inner.get("uri"):
        return (inner.get("uri") or "").strip() or None
    if inner is not None:
        u = getattr(inner, "uri", None)
        if u:
            return (u.strip() or None)
    return None


def _quoted_post_uri_from_post(post) -> str | None:
    """Extract quoted post URI from a PostView (quote repost embed). Returns None if not a quote."""
    record = _record_dict(post)
    embed = record.get("embed")
    if embed is None:
        embed = getattr(getattr(post, "record", None), "embed", None)
    return _get_embed_record_uri(embed)


def _parse_iso_datetime(s: str | None) -> datetime | None:
    """Parse ISO datetime string to UTC datetime. Returns None if s is empty or invalid."""
    if not s or not str(s).strip():
        return None
    raw = str(s).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _created_at_from_post(post) -> datetime | None:
    record = getattr(post, "record", None)
    raw = None
    if record is not None:
        raw = getattr(record, "created_at", None) or getattr(record, "createdAt", None)
        if raw is None and callable(getattr(record, "get", None)):
            raw = record.get("createdAt") or record.get("created_at")
    if not raw:
        # Fallback: indexed_at is always on PostView
        raw = getattr(post, "indexed_at", None) or getattr(post, "indexedAt", None)
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc)
    s = str(raw)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _followers_from_author(author) -> int | None:
    """Get follower count from author (ProfileViewBasic) when available."""
    if author is None:
        return None
    n = getattr(author, "followers_count", None) or getattr(author, "followersCount", None)
    if n is not None and isinstance(n, int) and n >= 0:
        return n
    if callable(getattr(author, "get", None)):
        n = author.get("followersCount") or author.get("followers_count")
        if n is not None and isinstance(n, int) and n >= 0:
            return n
    return None


def _has_media_from_post(post) -> int:
    record = _record_dict(post)
    embed = record.get("embed")
    if embed is None:
        embed = getattr(getattr(post, "record", None), "embed", None)
        
    if isinstance(embed, dict):
        t = embed.get("$type", "")
        if t in ("app.bsky.embed.images", "app.bsky.embed.video", "app.bsky.embed.external", "app.bsky.embed.recordWithMedia"):
            return 1
            
    t = getattr(embed, "$type", getattr(embed, "py_type", ""))
    if t in ("app.bsky.embed.images", "app.bsky.embed.video", "app.bsky.embed.external", "app.bsky.embed.recordWithMedia"):
        return 1
        
    return 0


def _backfill_authority(
    client: Client,
    keyword_matched_uris: set[str],
    since: str | None = None,
    until: str | None = None,
    verbose: bool = False,
    skip_filter: bool = False,
    max_pages_per_author: int = 5,
) -> list[tuple[str, str, str, datetime, int | None, int, int]]:
    """Fetch recent posts from each authority account; return (uri, cid, author_did, created_at, followers_count, keyword_matched).
    keyword_matched_uris: set of URIs that count as keyword-matched (DB + batch); updated when we add a matched post (for quote inclusion).
    If since/until are set, only posts with created_at in [since, until] are included (client-side filter). Feed is newest-first, so we stop when we see a post before since.
    """
    since_dt = _parse_iso_datetime(since)
    until_dt = _parse_iso_datetime(until)
    all_rows: list[tuple[str, str, str, datetime, int | None, int, int]] = []
    seen_uris: set[str] = set()
    for did, label in get_authority_accounts():
        cursor = None
        count_this = 0
        total_fetched = 0
        page = 0
        try:
            while True:
                if max_pages_per_author and page >= max_pages_per_author:
                    logger.info("Authority %s: hit max pages (%d), stopping", label, max_pages_per_author)
                    break
                import time
                try:
                    resp = client.app.bsky.feed.get_author_feed(
                        AuthorFeedParams(actor=did, limit=100, cursor=cursor, filter="posts_no_replies")
                    )
                except Exception as e:
                    if "429" in str(e) or "Too Many Requests" in str(e) or "ratelimit" in str(e).lower():
                        logger.warning("Rate limit hit on author feed %s, sleeping for 60s...", label)
                        time.sleep(60)
                        # Recreate client to ensure clean state after rate limit
                        client = Client()
                        client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
                        continue
                    raise
                feed = getattr(resp, "feed", []) or []
                if not feed:
                    if total_fetched == 0 and verbose:
                        logger.info("Authority %s: API returned empty feed", label)
                    break
                page += 1
                total_fetched += len(feed)
                break_before_since = False
                for item in feed:
                    post = getattr(item, "post", item)
                    uri = getattr(post, "uri", None)
                    if not uri or uri in seen_uris:
                        continue
                    text = _text_from_post(post)
                    keyword_matched = 1 if is_relevant_post(text) else 0
                    if not keyword_matched:
                        quoted_uri = _quoted_post_uri_from_post(post)
                        if quoted_uri and quoted_uri in keyword_matched_uris:
                            keyword_matched = 1
                    if not skip_filter and not keyword_matched:
                        if verbose:
                            logger.debug("Authority %s: skipped (filter) %.80r", label, (text or "")[:80])
                        continue
                    created = _created_at_from_post(post)
                    if not created:
                        if verbose:
                            logger.debug("Authority %s: skipped (no created_at) %s", label, uri[:60])
                        continue
                    if since_dt is not None and created < since_dt:
                        if verbose:
                            logger.debug("Authority %s: skipped (before --since) %s", label, uri[:60])
                        # Feed is newest-first; rest of this author's posts are older, so stop paginating
                        break_before_since = True
                        break
                    if until_dt is not None and created > until_dt:
                        if verbose:
                            logger.debug("Authority %s: skipped (after --until) %s", label, uri[:60])
                        continue
                    seen_uris.add(uri)
                    if keyword_matched:
                        keyword_matched_uris.add(uri)
                    cid = getattr(post, "cid", "") or ""
                    author = getattr(post, "author", None)
                    author_did = author.did if author else did
                    followers = _followers_from_author(author)
                    has_media = _has_media_from_post(post)
                    all_rows.append((uri, cid, author_did, created, followers, keyword_matched, has_media))
                    count_this += 1
                if break_before_since:
                    cursor = None
                else:
                    cursor = getattr(resp, "cursor", None)
                if not cursor:
                    break
            logger.info("Authority %s: %d matching posts (fetched %d items)", label, count_this, total_fetched)
        except Exception as e:
            logger.warning("Authority %s (%s): %s", label, did, e)
    return all_rows


# Max search pages per query (100 posts per page). Stops search from running forever.
DEFAULT_SEARCH_MAX_PAGES = 5

def _backfill_search(
    client: Client,
    keyword_matched_uris: set[str],
    since: str | None,
    until: str | None,
    verbose: bool = False,
    max_pages_per_query: int = DEFAULT_SEARCH_MAX_PAGES,
) -> list[tuple[str, str, str, datetime, int | None, int, int]]:
    """Search by keywords; return (uri, cid, author_did, created_at, followers_count, keyword_matched).
    Includes posts that match keywords or that quote a post in keyword_matched_uris.
    """
    seen: set[str] = set()
    to_insert: list[tuple[str, str, str, datetime, int | None, int]] = []
    for q in _get_search_queries():
        cursor = None
        total_posts_this_query = 0
        matched_this_query = 0
        page = 0
        try:
            while True:
                if max_pages_per_query and page >= max_pages_per_query:
                    logger.info("Search %r: hit max pages (%d), stopping", q, max_pages_per_query)
                    break
                import time
                try:
                    resp = client.app.bsky.feed.search_posts(
                        SearchPostsParams(q=q, limit=100, cursor=cursor, since=since, until=until)
                    )
                except Exception as e:
                    if "429" in str(e) or "Too Many Requests" in str(e) or "ratelimit" in str(e).lower():
                        logger.warning("Rate limit hit on search for %r, sleeping for 60s...", q)
                        time.sleep(60)
                        # Recreate client to ensure clean state after rate limit
                        client = Client()
                        client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
                        continue
                    raise
                posts = getattr(resp, "posts", []) or []
                if not posts:
                    if total_posts_this_query == 0 and verbose:
                        logger.info("Search %r: API returned no posts", q)
                    break
                page += 1
                total_posts_this_query += len(posts)
                for post in posts:
                    uri = getattr(post, "uri", None)
                    if not uri or uri in seen:
                        continue
                    text = _text_from_post(post)
                    keyword_matched = 1 if is_relevant_post(text) else 0
                    if not keyword_matched:
                        quoted_uri = _quoted_post_uri_from_post(post)
                        if quoted_uri and quoted_uri in keyword_matched_uris:
                            keyword_matched = 1
                    if not keyword_matched:
                        continue
                    author = getattr(post, "author", None)
                    author_did = getattr(author, "did", "") if author else ""
                    if not author_did:
                        if verbose:
                            logger.debug("Search %r: skipped (no author_did) %s", q, uri[:60])
                        continue
                    created = _created_at_from_post(post)
                    if not created:
                        if verbose:
                            logger.debug("Search %r: skipped (no created_at) %s", q, uri[:60])
                        continue
                    seen.add(uri)
                    keyword_matched_uris.add(uri)
                    cid = getattr(post, "cid", "") or ""
                    followers = _followers_from_author(author)
                    has_media = _has_media_from_post(post)
                    to_insert.append((uri, cid, author_did, created, followers, 1, has_media))
                    matched_this_query += 1
                cursor = getattr(resp, "cursor", None)
                if not cursor:
                    break
            logger.info(
                "Search %r: %d matching (fetched %d posts, %d unique so far)",
                q,
                matched_this_query,
                total_posts_this_query,
                len(seen),
            )
        except Exception as e:
            logger.warning("Search %r: %s", q, e)
    return to_insert


async def _write_batch(
    rows: list[tuple[str, str, str, datetime, int | None, int, int]],
    authority_dids: set[str],
) -> None:
    async with get_session() as session:
        for uri, cid, author_did, created_at, followers_count, keyword_matched, has_media in rows:
            await insert_post(session, uri, cid, author_did, created_at, keyword_matched=keyword_matched, has_media=has_media)
            if author_did in authority_dids:
                await upsert_user_authority(session, author_did, HARDCODED_AUTHORITY)
            else:
                await increment_user_match_count(session, author_did)
                await maybe_promote_authority(session, author_did, AUTHORITY_THRESHOLD, AUTHORITY_MULTIPLIER)
            if followers_count is not None:
                await update_user_followers(session, author_did, followers_count)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill PSU feed from authority accounts and keyword search")
    parser.add_argument("--authority-only", action="store_true", help="Only backfill authority account feeds")
    parser.add_argument("--search-only", action="store_true", help="Only backfill from keyword search")
    parser.add_argument(
        "--since",
        default=None,
        metavar="ISO",
        help="Only include posts after this time (search API; authority uses client-side filter). E.g. 2025-01-01T00:00:00.000Z",
    )
    parser.add_argument(
        "--until",
        default=None,
        metavar="ISO",
        help="Only include posts before this time (search API; authority uses client-side filter). E.g. 2025-12-31T23:59:59.000Z",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Log why posts are skipped (filter, no created_at, etc.)")
    parser.add_argument(
        "--authority-no-filter",
        action="store_true",
        help="Authority backfill: index all posts from authority accounts (ignore keyword filter). Use to confirm API returns data.",
    )
    parser.add_argument(
        "--search-max-pages",
        type=int,
        default=DEFAULT_SEARCH_MAX_PAGES,
        metavar="N",
        help="Max pagination pages per search query (default %d, 100 posts/page). 0 = no limit.",
    )
    parser.add_argument(
        "--authority-max-pages",
        type=int,
        default=5,
        metavar="N",
        help="Max pagination pages per authority account (default 5, 100 posts/page). 0 = no limit.",
    )
    args = parser.parse_args()
    do_authority = not args.search_only
    do_search = not args.authority_only

    if args.verbose:
        logging.getLogger(__name__).setLevel(logging.DEBUG)

    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        logger.error("Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD")
        raise SystemExit(1)

    async def _load_db_and_keyword_uris():
        await init_db()
        async with get_session() as session:
            return await get_keyword_matched_uris(session)

    keyword_matched_uris = asyncio.run(_load_db_and_keyword_uris())
    logger.info("Loaded %d existing keyword-matched URIs from DB (for quote-repost inclusion)", len(keyword_matched_uris))

    client = Client()
    client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)

    all_rows: list[tuple[str, str, str, datetime, int | None, int, int]] = []
    if do_authority and get_authority_accounts():
        auth_rows = _backfill_authority(
            client,
            keyword_matched_uris,
            since=args.since,
            until=args.until,
            verbose=args.verbose,
            skip_filter=args.authority_no_filter,
            max_pages_per_author=args.authority_max_pages,
        )
        all_rows.extend(auth_rows)
    if do_search:
        search_rows = _backfill_search(
            client,
            keyword_matched_uris,
            args.since,
            args.until,
            verbose=args.verbose,
            max_pages_per_query=args.search_max_pages,
        )
        # Dedupe by URI (authority might also appear in search)
        seen_uris = {r[0] for r in all_rows}
        for r in search_rows:
            if r[0] not in seen_uris:
                seen_uris.add(r[0])
                all_rows.append(r)

    if not all_rows:
        logger.info("No posts to insert")
        return
    logger.info("Inserting %d posts", len(all_rows))
    asyncio.run(_write_batch(all_rows, get_authority_dids()))
    logger.info("Backfill done. DB: %s", DATABASE_PATH)


if __name__ == "__main__":
    main()
