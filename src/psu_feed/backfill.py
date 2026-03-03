"""
Backfill the feed from historical data: authority accounts' posts and keyword search.

Run after setting BLUESKY_HANDLE and BLUESKY_APP_PASSWORD (same as publish).
  python -m psu_feed.backfill [--authority-only] [--search-only] [--since ISO] [--until ISO]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from atproto import Client
from atproto_client.models.app.bsky.feed.get_author_feed import Params as AuthorFeedParams
from atproto_client.models.app.bsky.feed.search_posts import Params as SearchPostsParams

from .authority_dids import AUTHORITY_ACCOUNTS, AUTHORITY_DIDS
from .config import BLUESKY_APP_PASSWORD, BLUESKY_HANDLE, DATABASE_PATH
from .db import (
    get_connection,
    init_db,
    insert_post,
    increment_user_match_count,
    maybe_promote_authority,
    update_user_followers,
    upsert_user_authority,
)
from .filter import is_relevant_post

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Authority multiplier for listed accounts
HARDCODED_AUTHORITY = 2.0
AUTHORITY_THRESHOLD = 10
AUTHORITY_MULTIPLIER = 1.5

# Search queries for keyword backfill (run each, dedupe by URI)
SEARCH_QUERIES = [
    "Penn State",
    "Nittany Lions",
    "PSU football",
    "Beaver Stadium",
    "Happy Valley",
]


def _text_from_post(post) -> str:
    # PostView can have .text at top level or inside .record
    text = getattr(post, "text", None)
    if not text:
        record = getattr(post, "record", None)
        if record is not None:
            text = getattr(record, "text", None) or (record.get("text") if callable(getattr(record, "get", None)) else None)
    return (text or "").strip()


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


def _backfill_authority(
    client: Client, verbose: bool = False, skip_filter: bool = False
) -> list[tuple[str, str, str, datetime, int | None, int]]:
    """Fetch recent posts from each authority account; return (uri, cid, author_did, created_at, followers_count, keyword_matched)."""
    all_rows: list[tuple[str, str, str, datetime, int | None, int]] = []
    seen_uris: set[str] = set()
    for did, label in AUTHORITY_ACCOUNTS:
        cursor = None
        count_this = 0
        total_fetched = 0
        try:
            while True:
                resp = client.app.bsky.feed.get_author_feed(
                    AuthorFeedParams(actor=did, limit=100, cursor=cursor, filter="posts_no_replies")
                )
                feed = getattr(resp, "feed", []) or []
                if not feed:
                    if total_fetched == 0 and verbose:
                        logger.info("Authority %s: API returned empty feed", label)
                    break
                total_fetched += len(feed)
                for item in feed:
                    post = getattr(item, "post", item)
                    uri = getattr(post, "uri", None)
                    if not uri or uri in seen_uris:
                        continue
                    text = _text_from_post(post)
                    keyword_matched = 1 if is_relevant_post(text) else 0
                    if not skip_filter and not keyword_matched:
                        if verbose:
                            logger.debug("Authority %s: skipped (filter) %.80r", label, (text or "")[:80])
                        continue
                    created = _created_at_from_post(post)
                    if not created:
                        if verbose:
                            logger.debug("Authority %s: skipped (no created_at) %s", label, uri[:60])
                        continue
                    seen_uris.add(uri)
                    cid = getattr(post, "cid", "") or ""
                    author = getattr(post, "author", None)
                    author_did = author.did if author else did
                    followers = _followers_from_author(author)
                    all_rows.append((uri, cid, author_did, created, followers, keyword_matched))
                    count_this += 1
                cursor = getattr(resp, "cursor", None)
                if not cursor:
                    break
            logger.info("Authority %s: %d matching posts (fetched %d items)", label, count_this, total_fetched)
        except Exception as e:
            logger.warning("Authority %s (%s): %s", label, did, e)
    return all_rows


# Max search pages per query (100 posts per page). Stops search from running forever.
DEFAULT_SEARCH_MAX_PAGES = 100


def _backfill_search(
    client: Client,
    since: str | None,
    until: str | None,
    verbose: bool = False,
    max_pages_per_query: int = DEFAULT_SEARCH_MAX_PAGES,
) -> list[tuple[str, str, str, datetime, int | None, int]]:
    """Search by keywords; return (uri, cid, author_did, created_at, followers_count, keyword_matched). Search only returns keyword-matched posts (keyword_matched=1)."""
    seen: set[str] = set()
    to_insert: list[tuple[str, str, str, datetime, int | None, int]] = []
    for q in SEARCH_QUERIES:
        cursor = None
        total_posts_this_query = 0
        matched_this_query = 0
        page = 0
        try:
            while True:
                if max_pages_per_query and page >= max_pages_per_query:
                    logger.info("Search %r: hit max pages (%d), stopping", q, max_pages_per_query)
                    break
                resp = client.app.bsky.feed.search_posts(
                    SearchPostsParams(q=q, limit=100, cursor=cursor, since=since, until=until)
                )
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
                    if not is_relevant_post(text):
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
                    cid = getattr(post, "cid", "") or ""
                    followers = _followers_from_author(author)
                    to_insert.append((uri, cid, author_did, created, followers, 1))
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
    rows: list[tuple[str, str, str, datetime, int | None, int]],
    authority_dids: set[str],
) -> None:
    conn = await get_connection()
    try:
        for uri, cid, author_did, created_at, followers_count, keyword_matched in rows:
            await insert_post(conn, uri, cid, author_did, created_at, keyword_matched=keyword_matched)
            if author_did in authority_dids:
                await upsert_user_authority(conn, author_did, HARDCODED_AUTHORITY)
            else:
                await increment_user_match_count(conn, author_did)
                await maybe_promote_authority(conn, author_did, AUTHORITY_THRESHOLD, AUTHORITY_MULTIPLIER)
            if followers_count is not None:
                await update_user_followers(conn, author_did, followers_count)
        await conn.commit()
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill PSU feed from authority accounts and keyword search")
    parser.add_argument("--authority-only", action="store_true", help="Only backfill authority account feeds")
    parser.add_argument("--search-only", action="store_true", help="Only backfill from keyword search")
    parser.add_argument(
        "--since",
        default=None,
        metavar="ISO",
        help="Search only: posts after this time (e.g. 2025-01-01T00:00:00.000Z)",
    )
    parser.add_argument(
        "--until",
        default=None,
        metavar="ISO",
        help="Search only: posts before this time (e.g. 2025-12-31T23:59:59.000Z)",
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
    args = parser.parse_args()
    do_authority = not args.search_only
    do_search = not args.authority_only

    if args.verbose:
        logging.getLogger(__name__).setLevel(logging.DEBUG)

    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        logger.error("Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD")
        raise SystemExit(1)

    asyncio.run(init_db())
    client = Client()
    client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)

    all_rows: list[tuple[str, str, str, datetime, int | None, int]] = []
    if do_authority and AUTHORITY_ACCOUNTS:
        auth_rows = _backfill_authority(
            client, verbose=args.verbose, skip_filter=args.authority_no_filter
        )
        all_rows.extend(auth_rows)
    if do_search:
        search_rows = _backfill_search(
            client,
            args.since,
            args.until,
            verbose=args.verbose,
            max_pages_per_query=args.search_max_pages if args.search_max_pages else None,
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
    asyncio.run(_write_batch(all_rows, AUTHORITY_DIDS))
    logger.info("Backfill done. DB: %s", DATABASE_PATH)


if __name__ == "__main__":
    main()
