"""LLM classifier for Penn State relevance. Uses Gemini 2.5 Flash Lite via google-genai."""

from __future__ import annotations

import json
import logging
import os

from google import genai
from google.genai.types import GenerateContentConfig

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are the gatekeeper to a Bluesky feed about all things Penn State. Your job is to classify Bluesky posts as either relevant or irrelevant. The posts are matched by user or keyword and then sent to you for evaluation. Relevant means the post is substantively about Penn State (university, athletics, community, alumni, etc.). Irrelevant means off-topic (e.g., unrelated sports, "PSU" as power supply, random keyword match). When a post quotes or reposts another post, consider both the outer post text and the "quoted_post" text together—relevance of either can make the whole post relevant. You can only respond with a single JSON array. Do not include any explanation or markdown.

Input format: a JSON array of objects. Each has "id" (post URI) and "post" (main post text). Optionally "quoted_post" (text of the quoted/reposted post) when the post is a quote.
Output format: a JSON array of objects with "id" (same URI) and "relevant" (boolean). One object per input post, same order.

Example input: [{"id": "at://did:plc:abc123/app.bsky.feed.post/xyz", "post": "This.", "quoted_post": "Penn State wins the White Out! We Are!"}]
Example output: [{"id": "at://did:plc:abc123/app.bsky.feed.post/xyz", "relevant": true}]"""

DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required for classification")
    return genai.Client(api_key=api_key)


async def classify_posts(posts: list[dict]) -> dict[str, bool]:
    """
    Classify a list of posts as relevant or not to Penn State.
    posts: list of {"id": uri, "post": text, "quoted_post": optional quoted text}
    Returns: dict mapping uri -> True (relevant) or False (irrelevant).
    """
    if not posts:
        return {}
    # Include posts that have main text and/or quoted text
    to_send = [
        p for p in posts
        if (p.get("post") or "").strip() or (p.get("quoted_post") or "").strip()
    ]
    if not to_send:
        return {p["id"]: False for p in posts}

    payload = json.dumps(to_send, ensure_ascii=False)
    model = os.environ.get("GEMINI_CLASSIFIER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    try:
        async with _get_client().aio as aclient:
            response = await aclient.models.generate_content(
                model=model,
                contents=payload,
                config=GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0,
                ),
            )
    except Exception as e:
        logger.exception("LLM classification failed: %s", e)
        # Treat all as rejected on failure so they can be retried
        return {p["id"]: False for p in posts}

    text = (response.text or "").strip()
    # Strip markdown code fence if present
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        results = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Classifier returned invalid JSON: %s", e)
        return {p["id"]: False for p in posts}

    if not isinstance(results, list):
        logger.warning("Classifier response was not a list: %s", type(results))
        return {p["id"]: False for p in posts}

    out: dict[str, bool] = {}
    for p in posts:
        uri = p["id"]
        out[uri] = False
    for item in results:
        if isinstance(item, dict) and "id" in item:
            uri = item.get("id")
            if uri is not None:
                out[str(uri)] = bool(item.get("relevant", False))
    return out
