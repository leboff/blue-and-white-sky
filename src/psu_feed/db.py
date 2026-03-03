"""SQLite schema and async DB helpers."""

from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

from .config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    did TEXT PRIMARY KEY,
    match_count INTEGER NOT NULL DEFAULT 0,
    authority_multiplier REAL NOT NULL DEFAULT 1.0,
    followers_count INTEGER
);

CREATE TABLE IF NOT EXISTS posts (
    uri TEXT PRIMARY KEY,
    cid TEXT,
    author_did TEXT NOT NULL,
    created_at TEXT NOT NULL,
    likes_count INTEGER NOT NULL DEFAULT 0,
    reposts_count INTEGER NOT NULL DEFAULT 0,
    keyword_matched INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (author_did) REFERENCES users(did)
);

CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at);
CREATE INDEX IF NOT EXISTS idx_posts_author_did ON posts(author_did);
"""


async def get_connection(db_path: Path | None = None) -> aiosqlite.Connection:
    path = db_path or DATABASE_PATH
    conn = await aiosqlite.connect(str(path))
    conn.row_factory = aiosqlite.Row
    return conn


async def init_db(db_path: Path | None = None) -> None:
    conn = await get_connection(db_path)
    try:
        await conn.executescript(SCHEMA)
        await conn.commit()
        # Migration: add followers_count to existing DBs (new installs already have it from SCHEMA)
        cursor = await conn.execute("PRAGMA table_info(users)")
        cols = [row[1] for row in await cursor.fetchall()]
        if "followers_count" not in cols:
            await conn.execute("ALTER TABLE users ADD COLUMN followers_count INTEGER")
            await conn.commit()
        # Migration: add keyword_matched to posts (authority posts included without keywords get 0)
        cursor = await conn.execute("PRAGMA table_info(posts)")
        pcols = [row[1] for row in await cursor.fetchall()]
        if "keyword_matched" not in pcols:
            await conn.execute("ALTER TABLE posts ADD COLUMN keyword_matched INTEGER NOT NULL DEFAULT 1")
            await conn.commit()
    finally:
        await conn.close()


async def insert_post(
    conn: aiosqlite.Connection,
    uri: str,
    cid: str,
    author_did: str,
    created_at: datetime,
    keyword_matched: int = 1,
) -> None:
    await conn.execute(
        "INSERT OR IGNORE INTO posts (uri, cid, author_did, created_at, keyword_matched) VALUES (?, ?, ?, ?, ?)",
        (uri, cid, author_did, created_at.isoformat(), keyword_matched),
    )


async def upsert_user_authority(conn: aiosqlite.Connection, did: str, authority_multiplier: float) -> None:
    await conn.execute(
        "INSERT INTO users (did, match_count, authority_multiplier) VALUES (?, 0, ?) "
        "ON CONFLICT(did) DO UPDATE SET authority_multiplier = excluded.authority_multiplier",
        (did, authority_multiplier),
    )


async def increment_user_match_count(conn: aiosqlite.Connection, did: str) -> None:
    await conn.execute(
        "INSERT INTO users (did, match_count, authority_multiplier) VALUES (?, 1, 1.0) "
        "ON CONFLICT(did) DO UPDATE SET match_count = match_count + 1",
        (did,),
    )


async def update_user_followers(conn: aiosqlite.Connection, did: str, followers_count: int) -> None:
    """Set or update follower count for a user (from profile when available)."""
    await conn.execute(
        "INSERT INTO users (did, match_count, authority_multiplier, followers_count) VALUES (?, 0, 1.0, ?) "
        "ON CONFLICT(did) DO UPDATE SET followers_count = excluded.followers_count",
        (did, followers_count),
    )


async def maybe_promote_authority(conn: aiosqlite.Connection, did: str, threshold: int = 10, multiplier: float = 1.5) -> None:
    await conn.execute(
        "UPDATE users SET authority_multiplier = ? WHERE did = ? AND match_count >= ? AND authority_multiplier < ?",
        (multiplier, did, threshold, multiplier),
    )


async def increment_likes(conn: aiosqlite.Connection, subject_uri: str) -> None:
    await conn.execute(
        "UPDATE posts SET likes_count = likes_count + 1 WHERE uri = ?",
        (subject_uri,),
    )


async def increment_reposts(conn: aiosqlite.Connection, subject_uri: str) -> None:
    await conn.execute(
        "UPDATE posts SET reposts_count = reposts_count + 1 WHERE uri = ?",
        (subject_uri,),
    )


async def delete_post(conn: aiosqlite.Connection, uri: str) -> bool:
    """Delete a post by URI. Returns True if a row was deleted."""
    cursor = await conn.execute("DELETE FROM posts WHERE uri = ?", (uri,))
    await conn.commit()
    return cursor.rowcount > 0


async def get_recent_posts_with_authority(
    conn: aiosqlite.Connection,
    lookback_hours: int,
) -> list[tuple[str, int, int, float, int | None, int, str]]:
    """Returns (uri, likes_count, reposts_count, authority_multiplier, followers_count, keyword_matched, created_at)."""
    cursor = await conn.execute(
        """
        SELECT p.uri, p.likes_count, p.reposts_count, COALESCE(u.authority_multiplier, 1.0), u.followers_count,
               COALESCE(p.keyword_matched, 1), p.created_at
        FROM posts p
        LEFT JOIN users u ON p.author_did = u.did
        WHERE datetime(p.created_at) >= datetime('now', ?)
        ORDER BY p.created_at DESC
        """,
        (f"-{lookback_hours} hours",),
    )
    rows = await cursor.fetchall()
    return [(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows]
