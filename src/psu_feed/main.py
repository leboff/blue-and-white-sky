"""FastAPI app: describeFeedGenerator and getFeedSkeleton (HN-ranked)."""

from __future__ import annotations

import html
import httpx
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import settings as settings_module
from .config import (
    FEED_DESCRIPTION,
    FEED_DISPLAY_NAME,
    FEED_LIMIT,
    FEED_RKEY,
    FEED_SERVICE_DID,
    GRAVITY,
    POSTS_LOOKBACK_HOURS,
)
from .db import delete_post, get_connection, get_recent_posts_with_authority
from .ranking import calculate_hn_score, effective_authority_multiplier

app = FastAPI(title="Penn State Football Feed")

BSKY_GET_POSTS_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts"


@app.get("/.well-known/did.json")
async def well_known_did(request: Request):
    """Serve did:web DID document so Bluesky can resolve FEED_SERVICE_DID to this server."""
    base = str(request.base_url).rstrip("/")
    return JSONResponse(
        content={
            "id": FEED_SERVICE_DID,
            "service": [
                {
                    "id": "#bsky_fg",
                    "type": "BskyFeedGenerator",
                    "serviceEndpoint": base,
                }
            ],
        }
    )


GET_POSTS_BATCH = 25


@app.get("/xrpc/app.bsky.feed.describeFeedGenerator")
async def describe_feed_generator():
    """List this server's feed URIs (caller uses this to discover feeds)."""
    feed_uri = f"at://{FEED_SERVICE_DID}/app.bsky.feed.generator/{FEED_RKEY}"
    return {
        "encoding": "application/json",
        "body": {
            "did": FEED_SERVICE_DID,
            "feeds": [
                {
                    "uri": feed_uri,
                    "displayName": FEED_DISPLAY_NAME,
                    "description": FEED_DESCRIPTION,
                }
            ],
        },
    }


@app.get("/xrpc/app.bsky.feed.getFeedSkeleton")
async def get_feed_skeleton(
    feed: str = Query(..., description="AT URI of the feed generator"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
):
    """
    Return a ranked list of post URIs (skeleton). Bluesky hydrates them.
    Ranked by HN-style score: (engagement * authority - 1) / (age_hours + 2)^gravity.
    """
    limit = min(limit, FEED_LIMIT)
    conn = await get_connection()
    try:
        rows = await get_recent_posts_with_authority(conn, POSTS_LOOKBACK_HOURS)
    finally:
        await conn.close()

    scored_initial = []
    for uri, likes, reposts, replies, has_media, mult, followers, keyword_matched, created_at, author_did in rows:
        base_score = calculate_hn_score(
            likes,
            reposts,
            replies,
            has_media,
            effective_authority_multiplier(mult, followers, keyword_matched),
            created_at,
            GRAVITY,
        )
        scored_initial.append((uri, base_score, author_did))
        
    scored_initial.sort(key=lambda x: -x[1])
    
    author_counts = {}
    scored = []
    for uri, score, author_did in scored_initial:
        count = author_counts.get(author_did, 0)
        diversity_penalty = 0.8 ** count
        final_score = score * diversity_penalty
        author_counts[author_did] = count + 1
        scored.append((uri, final_score))
        
    scored.sort(key=lambda x: -x[1])
    top = scored[:limit]
    feed_list = [{"post": uri} for uri, _ in top]

    # Optional cursor for pagination (e.g. last post URI or timestamp)
    next_cursor = None
    if len(scored) > limit and top:
        next_cursor = top[-1][0]

    return JSONResponse(
        content={
            "feed": feed_list,
            **({"cursor": next_cursor} if next_cursor else {}),
        }
    )


async def _get_ranked_skeleton(
    limit: int,
    lookback_hours: int,
    gravity: float,
) -> list[tuple[str, float]]:
    """Return [(uri, score), ...] for the top ranked posts."""
    conn = await get_connection()
    try:
        rows = await get_recent_posts_with_authority(conn, lookback_hours)
    finally:
        await conn.close()
        
    scored_initial = []
    for uri, likes, reposts, replies, has_media, mult, followers, keyword_matched, created_at, author_did in rows:
        base_score = calculate_hn_score(
            likes,
            reposts,
            replies,
            has_media,
            effective_authority_multiplier(mult, followers, keyword_matched),
            created_at,
            gravity,
        )
        scored_initial.append((uri, base_score, author_did))
        
    scored_initial.sort(key=lambda x: -x[1])
    
    author_counts = {}
    scored = []
    for uri, score, author_did in scored_initial:
        count = author_counts.get(author_did, 0)
        diversity_penalty = 0.8 ** count
        final_score = score * diversity_penalty
        author_counts[author_did] = count + 1
        scored.append((uri, final_score))
        
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


async def _get_ranked_skeleton_with_meta(
    limit: int,
    lookback_hours: int,
    gravity: float,
) -> list[tuple[str, float, float, int | None, str, str]]:
    """Return [(uri, score, effective_authority_multiplier, followers_count, created_at, author_did), ...] for dev view."""
    conn = await get_connection()
    try:
        rows = await get_recent_posts_with_authority(conn, lookback_hours)
    finally:
        await conn.close()
        
    scored_initial = []
    for uri, likes, reposts, replies, has_media, mult, followers, keyword_matched, created_at, author_did in rows:
        base_score = calculate_hn_score(
            likes,
            reposts,
            replies,
            has_media,
            effective_authority_multiplier(mult, followers, keyword_matched),
            created_at,
            gravity,
        )
        scored_initial.append((uri, base_score, effective_authority_multiplier(mult, followers, keyword_matched), followers, created_at, author_did))
        
    scored_initial.sort(key=lambda x: -x[1])
    
    author_counts = {}
    scored = []
    for item in scored_initial:
        uri, score, eff_mult, followers, created_at, author_did = item
        count = author_counts.get(author_did, 0)
        diversity_penalty = 0.8 ** count
        final_score = score * diversity_penalty
        author_counts[author_did] = count + 1
        scored.append((uri, final_score, eff_mult, followers, created_at, author_did))
        
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


async def _hydrate_posts(uris: list[str]) -> dict[str, dict]:
    """Fetch post views from Bluesky public API. Returns {uri: post_view_dict}."""
    out: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for i in range(0, len(uris), GET_POSTS_BATCH):
            batch = uris[i : i + GET_POSTS_BATCH]
            params = [("uris", u) for u in batch]
            r = await client.get(BSKY_GET_POSTS_URL, params=params)
            if r.status_code != 200:
                continue
            data = r.json()
            for post in data.get("posts") or []:
                uri = post.get("uri")
                if uri:
                    out[uri] = post
    return out


@app.get("/dev/feed")
async def dev_feed(
    limit: int = Query(20, ge=1, le=50),
    gravity: float = Query(None, description="HN gravity (default from config)"),
    lookback_hours: int = Query(None, description="Lookback hours (default from config)"),
):
    """
    Preview the feed with real post content. Use this to see what the feed returns
    and to tune gravity / lookback. Open in a browser: http://localhost:8000/dev/feed
    """
    g = gravity if gravity is not None else GRAVITY
    lookback = lookback_hours if lookback_hours is not None else POSTS_LOOKBACK_HOURS
    ranked = await _get_ranked_skeleton_with_meta(limit=limit, lookback_hours=lookback, gravity=g)
    if not ranked:
        html_body = "<p>No posts in the feed yet. Run the ingester and/or backfill to seed the DB.</p>"
    else:
        uris = [r[0] for r in ranked]
        hydrated = await _hydrate_posts(uris)
        # Compute live score (Bluesky API engagement) for each so order and displayed score are correct
        with_scores = []
        for uri, _db_score, mult, followers, created_at, author_did in ranked:
            post = hydrated.get(uri) or {}
            author = post.get("author") or {}
            handle = author.get("handle") or "?"
            display_name = author.get("displayName") or handle
            record = post.get("record") or {}
            text = record.get("text") or "(unable to load)"
            created = record.get("createdAt") or ""
            like_count = post.get("likeCount") or 0
            repost_count = post.get("repostCount") or 0
            reply_count = post.get("replyCount") or 0
            embed = record.get("embed")
            has_media = 0
            if isinstance(embed, dict):
                embed_type = embed.get("$type")
                if embed_type in ("app.bsky.embed.images", "app.bsky.embed.video", "app.bsky.embed.external", "app.bsky.embed.recordWithMedia"):
                    has_media = 1
            
            score = calculate_hn_score(like_count, repost_count, reply_count, has_media, mult, created_at, g)
            with_scores.append((score, uri, handle, display_name, text, like_count, repost_count, reply_count, created))
        with_scores.sort(key=lambda x: -x[0])
        rows = []
        for i, (score, uri, handle, display_name, text, like_count, repost_count, reply_count, created) in enumerate(with_scores, 1):
            uri_escaped = html.escape(uri, quote=True)
            rows.append(
                f"""
                <tr data-uri="{uri_escaped}">
                    <td>{i}</td>
                    <td><strong>{html.escape(display_name)}</strong> @{html.escape(handle)}</td>
                    <td>{html.escape(text[:200])}{"…" if len(text) > 200 else ""}</td>
                    <td>{like_count} / {repost_count} / {reply_count}</td>
                    <td>{score:.4f}</td>
                    <td>{html.escape(created[:19]) if created else ""}</td>
                    <td><a href="https://bsky.app/profile/{handle}/post/{uri.split('/')[-1]}" target="_blank">Open</a></td>
                    <td><button type="button" class="dev-feed-delete" data-uri="{uri_escaped}">Delete</button></td>
                </tr>
                """
            )
        html_body = f"""
        <p>Tuning: <a href="?limit={limit}&gravity=1.5&lookback_hours={lookback}">gravity=1.5</a> |
        <a href="?limit={limit}&gravity=1.8&lookback_hours={lookback}">1.8</a> |
        <a href="?limit={limit}&gravity={g}&lookback_hours=24">lookback=24h</a> |
        <a href="?limit={limit}&gravity={g}&lookback_hours=48">48h</a> |
        <a href="?limit={limit}&gravity={g}&lookback_hours=72">72h</a></p>
        <table border="1" cellpadding="8" style="border-collapse: collapse; width:100%;">
            <thead><tr>
                <th>#</th><th>Author</th><th>Text</th><th>Likes / Reposts / Replies</th><th>Score</th><th>Created</th><th>Link</th><th></th>
            </tr></thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
        <script>
        document.querySelectorAll('.dev-feed-delete').forEach(function(btn) {{
            btn.addEventListener('click', function() {{
                var uri = this.getAttribute('data-uri');
                if (!uri || !confirm('Delete this post from the DB?')) return;
                var row = this.closest('tr');
                fetch('/dev/feed/delete-post', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ uri: uri }})
                }}).then(function(r) {{
                    if (r.ok) row.remove();
                    else r.text().then(function(t) {{ alert('Delete failed: ' + t); }});
                }}).catch(function(e) {{ alert('Delete failed: ' + e); }});
            }});
        }});
        </script>
        """
    full = f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><title>PSU Feed Preview</title></head>
    <body>
        <h1>Penn State Feed — Preview</h1>
        {html_body}
    </body></html>
    """
    return HTMLResponse(full)


@app.post("/dev/feed/delete-post")
async def dev_feed_delete_post(body: dict = Body(...)):
    """Delete a post from the DB by URI (for dev feed cleanup)."""
    uri = body.get("uri")
    if not uri or not isinstance(uri, str):
        raise HTTPException(400, "body must include uri (string)")
    conn = await get_connection()
    try:
        deleted = await delete_post(conn, uri.strip())
    finally:
        await conn.close()
    if not deleted:
        raise HTTPException(404, "post not found")
    return {"ok": True}


# --- Admin UI (keywords & authorities) ---

def _validate_did(did: str) -> bool:
    return isinstance(did, str) and did.strip().startswith("did:")


@app.get("/admin/settings")
async def admin_get_settings():
    """Return current keywords, negative_keywords, and authorities for the admin UI."""
    return {
        "keywords": settings_module.get_keywords(),
        "negative_keywords": settings_module.get_negative_keywords(),
        "authorities": settings_module.get_authorities(),
    }


@app.put("/admin/settings")
async def admin_put_settings(body: dict = Body(...)):
    """Validate and save settings from the admin UI."""
    keywords = body.get("keywords")
    negative_keywords = body.get("negative_keywords")
    authorities = body.get("authorities")
    if keywords is not None and not isinstance(keywords, list):
        raise HTTPException(400, "keywords must be a list")
    if negative_keywords is not None and not isinstance(negative_keywords, list):
        raise HTTPException(400, "negative_keywords must be a list")
    if authorities is not None and not isinstance(authorities, list):
        raise HTTPException(400, "authorities must be a list")
    if isinstance(keywords, list) and not all(isinstance(k, str) for k in keywords):
        raise HTTPException(400, "keywords must be strings")
    if isinstance(negative_keywords, list) and not all(isinstance(k, str) for k in negative_keywords):
        raise HTTPException(400, "negative_keywords must be strings")
    if isinstance(authorities, list):
        for a in authorities:
            if not isinstance(a, dict) or not _validate_did(a.get("did") or ""):
                raise HTTPException(400, "authorities must be list of {did, label} with valid did")
            if "label" not in a:
                a["label"] = a.get("did", "")
    data = {
        "keywords": keywords if keywords is not None else settings_module.get_keywords(),
        "negative_keywords": negative_keywords if negative_keywords is not None else settings_module.get_negative_keywords(),
        "authorities": authorities if authorities is not None else settings_module.get_authorities(),
    }
    settings_module.save_settings(data)
    return {"ok": True}


ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PSU Feed — Admin</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 min-h-screen">
  <div class="max-w-4xl mx-auto px-4 py-8">
    <h1 class="text-2xl font-bold text-slate-800 mb-6">PSU Feed — Admin</h1>
    <p class="text-slate-600 mb-6">Manage keywords and authority accounts. Changes take effect after you click Save; the ingester picks them up within about 60 seconds.</p>

    <div id="message" class="mb-4 hidden rounded px-4 py-2"></div>

    <div class="grid gap-6 md:grid-cols-1">
      <!-- Keywords -->
      <section class="bg-white rounded-lg shadow p-5">
        <h2 class="text-lg font-semibold text-slate-800 mb-3">Keywords</h2>
        <ul id="keywords-list" class="space-y-2 mb-3"></ul>
        <div class="flex gap-2 flex-wrap">
          <input type="text" id="keyword-input" placeholder="Regex keyword (e.g. Nittany\\\\s?Lions?)" class="flex-1 min-w-[200px] border border-slate-300 rounded px-3 py-2">
          <button type="button" id="keyword-add" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Add</button>
        </div>
      </section>

      <!-- Negative keywords -->
      <section class="bg-white rounded-lg shadow p-5">
        <h2 class="text-lg font-semibold text-slate-800 mb-3">Negative keywords</h2>
        <ul id="negative-keywords-list" class="space-y-2 mb-3"></ul>
        <div class="flex gap-2 flex-wrap">
          <input type="text" id="negative-keyword-input" placeholder="Regex (e.g. Power\\\\s?Supply)" class="flex-1 min-w-[200px] border border-slate-300 rounded px-3 py-2">
          <button type="button" id="negative-keyword-add" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Add</button>
        </div>
      </section>

      <!-- Authorities -->
      <section class="bg-white rounded-lg shadow p-5">
        <h2 class="text-lg font-semibold text-slate-800 mb-3">Authorities</h2>
        <ul id="authorities-list" class="space-y-2 mb-3"></ul>
        <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <input type="text" id="authority-did" placeholder="DID (e.g. did:plc:...)" class="flex-1 min-w-[200px] border border-slate-300 rounded px-3 py-2">
          <input type="text" id="authority-label" placeholder="Label" class="flex-1 min-w-[120px] border border-slate-300 rounded px-3 py-2">
          <button type="button" id="authority-add" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Add</button>
        </div>
      </section>
    </div>

    <div class="mt-6 flex gap-3">
      <button type="button" id="save" class="bg-green-600 text-white px-5 py-2 rounded hover:bg-green-700">Save changes</button>
      <button type="button" id="reset" class="bg-slate-500 text-white px-5 py-2 rounded hover:bg-slate-600">Reset</button>
    </div>
  </div>

  <script>
    const messageEl = document.getElementById('message');
    function showMessage(text, isError) {
      messageEl.textContent = text;
      messageEl.className = 'mb-4 rounded px-4 py-2 ' + (isError ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800');
      messageEl.classList.remove('hidden');
    }
    function hideMessage() { messageEl.classList.add('hidden'); }

    let state = { keywords: [], negative_keywords: [], authorities: [] };

    function renderKeywords() {
      const ul = document.getElementById('keywords-list');
      ul.innerHTML = state.keywords.map((k, i) =>
        '<li class="flex items-center justify-between gap-2 py-1"><code class="text-sm bg-slate-100 px-2 py-0.5 rounded break-all">' + escapeHtml(k) + '</code><button type="button" class="delete-keyword text-red-600 hover:underline" data-i="' + i + '">Delete</button></li>'
      ).join('') || '<li class="text-slate-500 text-sm">No keywords yet.</li>';
      ul.querySelectorAll('.delete-keyword').forEach(btn => btn.addEventListener('click', () => { state.keywords.splice(+btn.dataset.i, 1); renderKeywords(); }));
    }
    function renderNegativeKeywords() {
      const ul = document.getElementById('negative-keywords-list');
      ul.innerHTML = state.negative_keywords.map((k, i) =>
        '<li class="flex items-center justify-between gap-2 py-1"><code class="text-sm bg-slate-100 px-2 py-0.5 rounded break-all">' + escapeHtml(k) + '</code><button type="button" class="delete-negative text-red-600 hover:underline" data-i="' + i + '">Delete</button></li>'
      ).join('') || '<li class="text-slate-500 text-sm">No negative keywords yet.</li>';
      ul.querySelectorAll('.delete-negative').forEach(btn => btn.addEventListener('click', () => { state.negative_keywords.splice(+btn.dataset.i, 1); renderNegativeKeywords(); }));
    }
    function renderAuthorities() {
      const ul = document.getElementById('authorities-list');
      ul.innerHTML = state.authorities.map((a, i) =>
        '<li class="flex items-center justify-between gap-2 py-1"><span class="text-sm"><code class="bg-slate-100 px-1 rounded">' + escapeHtml(a.did) + '</code> ' + escapeHtml(a.label || '') + '</span><button type="button" class="delete-authority text-red-600 hover:underline" data-i="' + i + '">Delete</button></li>'
      ).join('') || '<li class="text-slate-500 text-sm">No authorities yet.</li>';
      ul.querySelectorAll('.delete-authority').forEach(btn => btn.addEventListener('click', () => { state.authorities.splice(+btn.dataset.i, 1); renderAuthorities(); }));
    }
    function escapeHtml(s) {
      const div = document.createElement('div');
      div.textContent = s;
      return div.innerHTML;
    }

    async function load() {
      const r = await fetch('/admin/settings');
      if (!r.ok) throw new Error(r.statusText);
      state = await r.json();
      renderKeywords();
      renderNegativeKeywords();
      renderAuthorities();
    }
    document.getElementById('keyword-add').addEventListener('click', () => {
      const v = document.getElementById('keyword-input').value.trim();
      if (v) { state.keywords.push(v); document.getElementById('keyword-input').value = ''; renderKeywords(); }
    });
    document.getElementById('negative-keyword-add').addEventListener('click', () => {
      const v = document.getElementById('negative-keyword-input').value.trim();
      if (v) { state.negative_keywords.push(v); document.getElementById('negative-keyword-input').value = ''; renderNegativeKeywords(); }
    });
    document.getElementById('authority-add').addEventListener('click', () => {
      const did = document.getElementById('authority-did').value.trim();
      const label = document.getElementById('authority-label').value.trim();
      if (did && did.startsWith('did:')) { state.authorities.push({ did, label: label || did }); document.getElementById('authority-did').value = ''; document.getElementById('authority-label').value = ''; renderAuthorities(); } else { showMessage('DID must start with did:', true); }
    });
    document.getElementById('save').addEventListener('click', async () => {
      hideMessage();
      try {
        const r = await fetch('/admin/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(state) });
        if (!r.ok) { const t = await r.text(); throw new Error(t || r.statusText); }
        showMessage('Saved.', false);
      } catch (e) { showMessage(e.message || 'Save failed', true); }
    });
    document.getElementById('reset').addEventListener('click', () => { load(); hideMessage(); });

    load();
  </script>
</body>
</html>
"""


@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
async def admin_page():
    """Serve the admin UI for keywords and authorities."""
    return HTMLResponse(ADMIN_HTML)
