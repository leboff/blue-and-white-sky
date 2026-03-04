"""Hacker News decay ranking for feed skeleton."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from .config import AUTHORITY_OFFTOPIC_PENALTY, FRESH_POST_SCORE_FLOOR

def serendipity_boost(age_hours: float) -> float:
    """Give a 2x artificial point boost that decays to 1x over the first 2 hours."""
    if age_hours < 2.0:
        return 1.0 + (1.0 - (age_hours / 2.0))
    return 1.0

def get_dynamic_gravity(base_gravity: float) -> float:
    """Increase gravity on Game Days (Saturdays in Fall) to make the feed faster."""
    now = datetime.now(timezone.utc)
    # College football season is roughly Sept (9) to Dec (12).
    # Saturday is weekday() == 5
    if 9 <= now.month <= 12 and now.weekday() == 5:
        return base_gravity + 0.5  # Faster decay on Game Day
    return base_gravity

# Max boost from followers (e.g. 1.5 = up to 50% boost). Tuned so 10k followers ~ 1.2x, 100k ~ 1.4x.
FOLLOWER_BOOST_MAX = 0.5

def follower_boost(followers_count: int | None) -> float:
    """Multiplier from follower count: 1.0 when unknown/0, up to 1 + FOLLOWER_BOOST_MAX for large accounts."""
    if followers_count is None or followers_count <= 0:
        return 1.0
    # log10(1 + n): 1k -> ~3, 10k -> ~4, 100k -> ~5. Scale so 100k hits cap.
    log = math.log10(1 + followers_count)
    return 1.0 + min(FOLLOWER_BOOST_MAX, log / 10.0)


def effective_authority_multiplier(
    base_mult: float,
    followers_count: int | None,
    keyword_matched: int = 1,
) -> float:
    """Authority multiplier = base * follower_boost * (1.0 or AUTHORITY_OFFTOPIC_PENALTY if no keyword match)."""
    mult = base_mult * follower_boost(followers_count)
    if keyword_matched:
        return mult
    return mult * AUTHORITY_OFFTOPIC_PENALTY


def calculate_hn_score(
    likes: int,
    reposts: int,
    replies: int,
    has_media: int,
    multiplier: float,
    created_at: datetime | str,
    gravity: float = 1.5,
) -> float:
    """
    Score = max(FLOOR, P - 1) / (T + 2)^G
    P = (likes + reposts * 1.5 + replies * 0.5) * authority_multiplier * media_boost * serendipity_boost.
    T = age in hours. FLOOR ensures new posts with no engagement still get a positive score so they appear; they decay with age.
    """
    if isinstance(created_at, str):
        try:
            if created_at.endswith("Z"):
                created_at = created_at[:-1] + "+00:00"
            created_at = datetime.fromisoformat(created_at).astimezone(timezone.utc)
        except (ValueError, TypeError):
            created_at = datetime.now(timezone.utc)
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_seconds = (now - created_at).total_seconds()
    age_hours = max(0.0, age_seconds / 3600.0)

    media_boost = 1.2 if has_media else 1.0
    s_boost = serendipity_boost(age_hours)
    
    # Reposts are highly visible, replies show engagement but can be noise
    engagement = (likes * 1.0) + (reposts * 1.5) + (replies * 0.5)
    points = engagement * multiplier * media_boost * s_boost
    # Floor so new posts with no engagement still appear; they decay with age
    adjusted_points = max(FRESH_POST_SCORE_FLOOR, points - 1.0)
    
    dynamic_grav = get_dynamic_gravity(gravity)
    denominator = (age_hours + 2.0) ** dynamic_grav
    if denominator <= 0:
        return 0.0
    return adjusted_points / denominator
