"""Keyword and heuristic filter for Penn State football posts."""

POSITIVE_TERMS = [
    "penn state",
    "nittany lions",
    "james franklin",
    "beaver stadium",
    "we are",
]
NEGATIVE_TERMS = [
    "watt",
    "corsair",
    "evga",
    "voltage",
    "portland",
]


def is_relevant_post(text: str) -> bool:
    """True if the post matches PSU football keywords and passes negative filter."""
    if not text or not text.strip():
        return False
    text_lower = text.lower()
    has_positive = any(term in text_lower for term in POSITIVE_TERMS) or "psu" in text_lower
    if not has_positive:
        return False
    has_negative = any(term in text_lower for term in NEGATIVE_TERMS)
    return not has_negative
