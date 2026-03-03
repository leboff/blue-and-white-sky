"""Hacker News decay ranking for feed skeleton."""

from __future__ import annotations

from datetime import datetime, timezone


def calculate_hn_score(
    likes: int,
    reposts: int,
    multiplier: float,
    created_at: datetime | str,
    gravity: float = 1.5,
) -> float:
    """
    Score = (P - 1) / (T + 2)^G
    P = (likes + reposts) * authority_multiplier, minus 1 for author's implicit point.
    T = age in hours.
    """
    points = (likes + reposts) * multiplier
    adjusted_points = max(0.0, points - 1.0)
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
    denominator = (age_hours + 2.0) ** gravity
    if denominator <= 0:
        return 0.0
    return adjusted_points / denominator
