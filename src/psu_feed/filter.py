"""Keyword and heuristic filter for Penn State football posts."""

from . import settings


def is_relevant_post(text: str) -> bool:
    """True if the post matches PSU football keywords and passes negative filter."""
    if not text or not text.strip():
        return False
    if not settings.get_compiled_positive_pattern().search(text):
        return False
    if settings.get_compiled_negative_pattern().search(text):
        return False
    return True
