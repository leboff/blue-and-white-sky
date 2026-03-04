"""SQLModel table definitions for User and Post."""

from __future__ import annotations

from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    did: str = Field(primary_key=True)
    match_count: int = Field(default=0)
    authority_multiplier: float = Field(default=1.0)
    followers_count: Optional[int] = None


class Post(SQLModel, table=True):
    __tablename__ = "posts"

    uri: str = Field(primary_key=True)
    cid: Optional[str] = None
    author_did: str = Field(foreign_key="users.did")
    created_at: str = Field()  # ISO format stored in DB
    likes_count: int = Field(default=0)
    reposts_count: int = Field(default=0)
    replies_count: int = Field(default=0)
    has_media: int = Field(default=0)
    keyword_matched: int = Field(default=1)
    llm_approved: int = Field(default=1)  # 0=pending, 1=approved, 2=rejected
    post_text: Optional[str] = None
    quoted_post_uri: Optional[str] = None


class PostWithAuthority(SQLModel):
    """Read model for feed ranking: post row joined with user authority."""

    uri: str
    likes_count: int
    reposts_count: int
    replies_count: int
    has_media: int
    authority_multiplier: float
    followers_count: Optional[int]
    keyword_matched: int
    created_at: str
    author_did: str
    llm_approved: int
