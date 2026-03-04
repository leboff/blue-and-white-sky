#!/usr/bin/env python3
"""
Volume/cost estimates for LLM classifier (Gemini 2.5 Flash Lite).
Run from repo root: python scripts/cost_estimate.py
"""
from __future__ import annotations

# From classifier.py (system instruction only)
SYSTEM_INSTRUCTION = """You are the gatekeeper to a Bluesky feed about all things Penn State. Your job is to classify Bluesky posts as either relevant or irrelevant. The posts are matched by user or keyword and then sent to you for evaluation. Relevant means the post is substantively about Penn State (university, athletics, community, alumni, etc.). Irrelevant means off-topic (e.g., unrelated sports, "PSU" as power supply, random keyword match). You can only respond with a single JSON array. Do not include any explanation or markdown.

Input format: a JSON array of objects with "id" (post URI) and "post" (post text).
Output format: a JSON array of objects with "id" (same URI) and "relevant" (boolean). One object per input post, same order.

Example input: [{"id": "at://did:plc:abc123/app.bsky.feed.post/xyz", "post": "Can't wait for the White Out game this weekend! We Are!"}]
Example output: [{"id": "at://did:plc:abc123/app.bsky.feed.post/xyz", "relevant": true}]"""

# Gemini 2.5 Flash Lite (Google AI API)
INPUT_USD_PER_1M = 0.10
OUTPUT_USD_PER_1M = 0.40

# Rough tokens (English/JSON: ~4 chars per token)
CHARS_PER_TOKEN = 4


def main() -> None:
    sys_chars = len(SYSTEM_INSTRUCTION)
    sys_tokens = sys_chars // CHARS_PER_TOKEN

    # Typical: URI ~70 chars, post text 50–300 chars (use 150 avg)
    uri_len = 70
    post_len_avg = 150
    # One input object: {"id": "<uri>", "post": "<text>"} + commas
    input_chars_per_post = uri_len + post_len_avg + 30  # +30 for keys/quotes
    # One output object: {"id": "<uri>", "relevant": true}
    output_chars_per_post = uri_len + 25

    print("=== LLM classifier volume/cost (Gemini 2.5 Flash Lite) ===\n")
    print("Assumptions:")
    print(f"  System instruction: {sys_chars} chars ≈ {sys_tokens} tokens")
    print(f"  Per post input:     ~{input_chars_per_post} chars (URI + ~{post_len_avg} char text)")
    print(f"  Per post output:   ~{output_chars_per_post} chars (id + relevant)")
    print(f"  Tokens ≈ chars / {CHARS_PER_TOKEN}")
    print(f"  Pricing: ${INPUT_USD_PER_1M}/1M input, ${OUTPUT_USD_PER_1M}/1M output\n")

    for n in [1, 10, 20, 50]:
        in_tok = sys_tokens + (input_chars_per_post * n) // CHARS_PER_TOKEN
        out_tok = (output_chars_per_post * n) // CHARS_PER_TOKEN
        cost_in = in_tok * (INPUT_USD_PER_1M / 1_000_000)
        cost_out = out_tok * (OUTPUT_USD_PER_1M / 1_000_000)
        total = cost_in + cost_out
        per_post = total / n if n else 0
        print(f"  Batch of {n:3d} posts:  input {in_tok:5d} tok, output {out_tok:4d} tok  →  ${total:.6f}  (${per_post:.6f}/post)")

    print("\n--- Daily volume scenarios (posts that need classification) ---\n")
    scenarios = [
        ("Light (e.g. few keywords)", 200),
        ("Medium (broader keywords)", 1_500),
        ("Heavy (game day / many authorities)", 5_000),
        ("Max (50 every 60s, 24h)", 50 * 24 * 60),
    ]
    for label, posts_per_day in scenarios:
        # Batches of 50, so number of API calls
        batches = (posts_per_day + 49) // 50
        # Tokens per batch (use 50-post batch for simplicity; last batch may be smaller)
        n = min(50, posts_per_day)
        in_tok = sys_tokens + (input_chars_per_post * n) // CHARS_PER_TOKEN
        out_tok = (output_chars_per_post * n) // CHARS_PER_TOKEN
        cost_per_batch = in_tok * (INPUT_USD_PER_1M / 1_000_000) + out_tok * (OUTPUT_USD_PER_1M / 1_000_000)
        # For variable batch sizes, approximate: total posts * per-post cost at 50-post rate
        avg_per_post = (in_tok / n) * (INPUT_USD_PER_1M / 1_000_000) + (out_tok / n) * (OUTPUT_USD_PER_1M / 1_000_000)
        daily = posts_per_day * avg_per_post
        monthly = daily * 30
        print(f"  {label}: {posts_per_day:,} posts/day  →  ~${daily:.2f}/day  (~${monthly:.1f}/month)")

    print("\n--- Summary ---")
    print("  Cost is dominated by output (fewer tokens but 4× price). Batching 50 posts per call")
    print("  keeps API calls and system-instruction overhead low. At Flash Lite pricing, even")
    print("  heavy use stays on the order of a few dollars per month.")


if __name__ == "__main__":
    main()
