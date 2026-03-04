"""Database access: async session and repository functions. Use get_session() for all DB work."""

from __future__ import annotations

from .models import PostWithAuthority
from .repositories import (
    delete_post,
    get_keyword_matched_uris,
    get_pending_posts,
    get_recent_posts_with_authority,
    get_session,
    increment_likes,
    increment_replies,
    increment_reposts,
    init_db,
    insert_post,
    maybe_promote_authority,
    post_has_keyword_match,
    update_post_classification,
    update_user_followers,
    upsert_user_authority,
    increment_user_match_count,
)

__all__ = [
    "PostWithAuthority",
    "delete_post",
    "get_keyword_matched_uris",
    "get_pending_posts",
    "get_recent_posts_with_authority",
    "get_session",
    "increment_likes",
    "increment_replies",
    "increment_reposts",
    "init_db",
    "insert_post",
    "maybe_promote_authority",
    "post_has_keyword_match",
    "update_post_classification",
    "update_user_followers",
    "upsert_user_authority",
    "increment_user_match_count",
]
