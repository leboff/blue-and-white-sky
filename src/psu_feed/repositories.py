"""Repository layer for Post and User. Use via db.get_session() and db module functions."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlmodel import select

from .config import DATABASE_PATH
from .models import Post, PostWithAuthority, User

# Async engine and session factory
def _database_url(path: Path | None = None) -> str:
    p = path or DATABASE_PATH
    return f"sqlite+aiosqlite:///{p}"

_engine = create_async_engine(_database_url(), echo=False)
_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session(db_path: Path | None = None) -> AsyncIterator[AsyncSession]:
    """Async context manager yielding an AsyncSession. Use for all DB access."""
    if db_path is not None and str(db_path) != str(DATABASE_PATH):
        engine = create_async_engine(_database_url(db_path), echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    else:
        factory = _session_factory
    async with factory() as session:
        yield session


async def init_db(db_path: Path | None = None) -> None:
    """Create tables and run migrations."""
    from sqlmodel import SQLModel
    engine = create_async_engine(_database_url(db_path), echo=False) if db_path else _engine
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: SQLModel.metadata.create_all(sync_conn.engine))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await _run_migrations(session)


async def _run_migrations(session: AsyncSession) -> None:
    """Add missing columns to existing databases."""
    r = await session.execute(text("PRAGMA table_info(users)"))
    cols = [row[1] for row in r.fetchall()]
    if "followers_count" not in cols:
        await session.execute(text("ALTER TABLE users ADD COLUMN followers_count INTEGER"))
    r = await session.execute(text("PRAGMA table_info(posts)"))
    pcols = [row[1] for row in r.fetchall()]
    for col, defn in [
        ("keyword_matched", "INTEGER NOT NULL DEFAULT 1"),
        ("replies_count", "INTEGER NOT NULL DEFAULT 0"),
        ("has_media", "INTEGER NOT NULL DEFAULT 0"),
        ("llm_approved", "INTEGER NOT NULL DEFAULT 1"),
        ("post_text", "TEXT"),
        ("quoted_post_uri", "TEXT"),
    ]:
        if col not in pcols:
            await session.execute(text(f"ALTER TABLE posts ADD COLUMN {col} {defn}"))
    await session.commit()


# --- Post repository (module-level functions taking session) ---

async def insert_post(
    session: AsyncSession,
    uri: str,
    cid: str,
    author_did: str,
    created_at: datetime,
    keyword_matched: int = 1,
    has_media: int = 0,
    llm_approved: int = 1,
    post_text: str | None = None,
    quoted_post_uri: str | None = None,
) -> None:
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    stmt = sqlite_insert(Post).values(
        uri=uri, cid=cid, author_did=author_did, created_at=created_at.isoformat(),
        keyword_matched=keyword_matched, has_media=has_media, llm_approved=llm_approved,
        post_text=post_text, quoted_post_uri=quoted_post_uri,
    ).on_conflict_do_nothing(index_elements=["uri"])
    await session.execute(stmt)
    await session.commit()


async def delete_post(session: AsyncSession, uri: str) -> bool:
    r = await session.execute(select(Post).where(Post.uri == uri))
    post = r.scalar_one_or_none()
    if post is None:
        return False
    await session.delete(post)
    await session.commit()
    return True


async def get_recent_posts_with_authority(
    session: AsyncSession,
    lookback_hours: int,
    include_pending_rejected: bool = False,
    cursor_uri: str | None = None,
    limit: int | None = None,
) -> list[PostWithAuthority]:
    where_llm = "" if include_pending_rejected else " AND p.llm_approved = 1"
    where_cursor = ""
    if cursor_uri:
        where_cursor = " AND (datetime(p.created_at), p.uri) < (SELECT datetime(created_at), uri FROM posts WHERE uri = :cursor_uri)"
    limit_clause = "" if limit is None else " LIMIT :limit"
    sql = text(f"""
        SELECT p.uri, p.likes_count, p.reposts_count, p.replies_count, p.has_media,
               COALESCE(u.authority_multiplier, 1.0) AS authority_multiplier, u.followers_count,
               COALESCE(p.keyword_matched, 1) AS keyword_matched, p.created_at, p.author_did, COALESCE(p.llm_approved, 1) AS llm_approved
        FROM posts p
        LEFT JOIN users u ON p.author_did = u.did
        WHERE datetime(p.created_at) >= datetime('now', :lookback){where_llm}{where_cursor}
        ORDER BY p.created_at DESC{limit_clause}
    """)
    params: dict = {"lookback": f"-{lookback_hours} hours"}
    if cursor_uri:
        params["cursor_uri"] = cursor_uri
    if limit is not None:
        params["limit"] = limit
    r = await session.execute(sql, params)
    rows = r.fetchall()
    return [
        PostWithAuthority(
            uri=row[0],
            likes_count=row[1],
            reposts_count=row[2],
            replies_count=row[3],
            has_media=row[4],
            authority_multiplier=row[5],
            followers_count=row[6],
            keyword_matched=row[7],
            created_at=row[8],
            author_did=row[9],
            llm_approved=row[10],
        )
        for row in rows
    ]


async def get_pending_posts(
    session: AsyncSession,
    limit: int = 50,
) -> list[tuple[str, str, str | None]]:
    r = await session.execute(
        select(Post.uri, Post.post_text, Post.quoted_post_uri)
        .where(Post.llm_approved == 0)
        .order_by(Post.created_at.desc())
        .limit(limit)
    )
    rows = r.fetchall()
    return [(row[0], row[1] or "", row[2]) for row in rows]


async def update_post_classification(
    session: AsyncSession,
    updates: list[tuple[str, int]],
) -> None:
    for uri, llm_approved in updates:
        r = await session.execute(select(Post).where(Post.uri == uri))
        post = r.scalar_one_or_none()
        if post:
            post.llm_approved = llm_approved
    await session.commit()


async def increment_likes(session: AsyncSession, subject_uri: str) -> None:
    r = await session.execute(select(Post).where(Post.uri == subject_uri))
    post = r.scalar_one_or_none()
    if post:
        post.likes_count = (post.likes_count or 0) + 1
        await session.commit()


async def increment_reposts(session: AsyncSession, subject_uri: str) -> None:
    r = await session.execute(select(Post).where(Post.uri == subject_uri))
    post = r.scalar_one_or_none()
    if post:
        post.reposts_count = (post.reposts_count or 0) + 1
        await session.commit()


async def increment_replies(session: AsyncSession, subject_uri: str) -> None:
    r = await session.execute(select(Post).where(Post.uri == subject_uri))
    post = r.scalar_one_or_none()
    if post:
        post.replies_count = (post.replies_count or 0) + 1
        await session.commit()


async def update_post_engagement(
    session: AsyncSession,
    uri: str,
    likes_count: int,
    reposts_count: int,
    replies_count: int,
) -> None:
    """Set a post's engagement counts (e.g. from Bluesky getPosts). Used to refresh ranking data."""
    r = await session.execute(select(Post).where(Post.uri == uri))
    post = r.scalar_one_or_none()
    if post:
        post.likes_count = likes_count
        post.reposts_count = reposts_count
        post.replies_count = replies_count
        await session.commit()


async def update_posts_engagement_bulk(
    session: AsyncSession,
    updates: list[tuple[str, int, int, int]],
) -> None:
    """Set engagement counts for many posts. Each item is (uri, likes_count, reposts_count, replies_count)."""
    for uri, likes_count, reposts_count, replies_count in updates:
        r = await session.execute(select(Post).where(Post.uri == uri))
        post = r.scalar_one_or_none()
        if post:
            post.likes_count = likes_count
            post.reposts_count = reposts_count
            post.replies_count = replies_count
    await session.commit()


async def post_has_keyword_match(session: AsyncSession, uri: str) -> bool:
    r = await session.execute(select(Post).where(Post.uri == uri, Post.keyword_matched == 1))
    return r.scalar_one_or_none() is not None


async def get_keyword_matched_uris(session: AsyncSession) -> set[str]:
    r = await session.execute(select(Post.uri).where(Post.keyword_matched == 1))
    return {row[0] for row in r.fetchall()}


# --- User repository ---

async def upsert_user_authority(session: AsyncSession, did: str, authority_multiplier: float) -> None:
    r = await session.execute(select(User).where(User.did == did))
    user = r.scalar_one_or_none()
    if user:
        user.authority_multiplier = authority_multiplier
    else:
        session.add(User(did=did, match_count=0, authority_multiplier=authority_multiplier))
    await session.commit()


async def increment_user_match_count(session: AsyncSession, did: str) -> None:
    r = await session.execute(select(User).where(User.did == did))
    user = r.scalar_one_or_none()
    if user:
        user.match_count = (user.match_count or 0) + 1
    else:
        session.add(User(did=did, match_count=1, authority_multiplier=1.0))
    await session.commit()


async def update_user_followers(session: AsyncSession, did: str, followers_count: int) -> None:
    r = await session.execute(select(User).where(User.did == did))
    user = r.scalar_one_or_none()
    if user:
        user.followers_count = followers_count
    else:
        session.add(User(did=did, match_count=0, authority_multiplier=1.0, followers_count=followers_count))
    await session.commit()


async def maybe_promote_authority(
    session: AsyncSession, did: str, threshold: int = 10, multiplier: float = 1.5
) -> None:
    r = await session.execute(select(User).where(User.did == did))
    user = r.scalar_one_or_none()
    if user and (user.match_count or 0) >= threshold and (user.authority_multiplier or 0) < multiplier:
        user.authority_multiplier = multiplier
        await session.commit()
