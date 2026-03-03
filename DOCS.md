# Blue and White Sky — Documentation

A custom Bluesky feed that curates **Penn State football** content: it ingests posts from the firehose (Jetstream), filters by keywords, tracks engagement and authority, and serves a ranked feed using a Hacker News–style decay algorithm.

---

## Architecture overview

```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Bluesky Jetstream  │────▶│  Python Ingester │────▶│   SQLite    │
│  (WebSocket)        │     │  (filter + store)│     │   (posts,   │
└─────────────────────┘     └──────────────────┘     │    users)   │
        │                             │               └──────┬──────┘
        │ likes/reposts               │                      │
        ▼                             ▼                      │
┌─────────────────────┐     ┌──────────────────┐           │
│  app.bsky.feed.like │     │  Keyword filter   │           │
│  app.bsky.feed.     │     │  (PSU football +  │           │
│  repost             │     │   negative list)  │           │
└─────────────────────┘     └──────────────────┘           │
                                                             │
┌─────────────────────┐     ┌──────────────────┐           │
│  Bluesky app        │────▶│  FastAPI server  │◀──────────┘
│  (getFeedSkeleton)  │     │  HN ranking +    │
└─────────────────────┘     │  skeleton response│
                            └──────────────────┘
```

- **Ingester**: Connects to Jetstream, handles `app.bsky.feed.post`, `app.bsky.feed.like`, `app.bsky.feed.repost`. Filters posts with the PSU keyword filter, inserts posts and updates user authority / engagement in SQLite.
- **Backfill**: One-off or occasional historical load via Bluesky API (author feeds + keyword search). Populates posts and, when available, follower counts.
- **API**: Serves `describeFeedGenerator` and `getFeedSkeleton`. Ranking uses HN-style score with authority and follower boost.
- **Publish script**: Creates the `app.bsky.feed.generator` record on your account so the feed appears in Bluesky.

---

## Project layout

| Path | Purpose |
|------|--------|
| `src/psu_feed/config.py` | Env-based config (DB, Jetstream URL, feed metadata, gravity, lookback). |
| `src/psu_feed/db.py` | SQLite schema and async helpers (posts, users, init, insert, authority, engagement). |
| `src/psu_feed/filter.py` | PSU football keyword regex (positive/negative) and `is_relevant_post()`. |
| `src/psu_feed/authority_dids.py` | List of (DID, label) for accounts that get a fixed 2.0× authority multiplier. |
| `src/psu_feed/ranking.py` | HN score formula, follower boost, `effective_authority_multiplier()`. |
| `src/psu_feed/ingester.py` | Jetstream WebSocket client: filter posts, store posts/users, track likes/reposts. |
| `src/psu_feed/main.py` | FastAPI app: `getFeedSkeleton`, `describeFeedGenerator`, `/dev/feed` preview. |
| `src/psu_feed/backfill.py` | Backfill from authority feeds + keyword search; stores posts and follower counts. |
| `src/psu_feed/publish_feed.py` | Publishes the feed generator record to your Bluesky account. |

---

## Configuration (environment)

Loaded from `.env` in the project root (via `python-dotenv`). Main variables:

| Variable | Purpose |
|----------|--------|
| `BLUESKY_HANDLE` | Your Bluesky handle (for publish and backfill). |
| `BLUESKY_APP_PASSWORD` | Bluesky App Password (not your account password). |
| `FEED_SERVICE_DID` | DID of the feed service (e.g. `did:web:yourdomain.com` in production). |
| `FEED_RKEY` | Record key for the feed (default `psu-football`). |
| `FEED_DISPLAY_NAME`, `FEED_DESCRIPTION` | Shown in Bluesky for the feed. |
| `DATABASE_PATH` | SQLite file path (default `./data/psu_feed.db`). |
| `JETSTREAM_WS_URL` | Jetstream WebSocket URL (default US-East). |
| `AUTHORITY_DIDS` | Optional comma-separated DIDs to add to the authority set (on top of `authority_dids.py`). |
| `PSU_FEED_GRAVITY` | HN gravity (default `1.5`). |
| `PSU_FEED_LOOKBACK_HOURS` | How many hours of posts to consider when ranking (default `48`). |

---

## Database schema

**`users`**

| Column | Type | Description |
|--------|------|-------------|
| `did` | TEXT PK | User DID. |
| `match_count` | INTEGER | Number of posts that passed the keyword filter (used for 1.5× promotion). |
| `authority_multiplier` | REAL | Base multiplier: 1.0, 1.5 (after 10+ matches), or 2.0 for authority DIDs. |
| `followers_count` | INTEGER | Follower count when known (from backfill); used for follower boost. |

**`posts`**

| Column | Type | Description |
|--------|------|-------------|
| `uri` | TEXT PK | Post AT URI. |
| `cid` | TEXT | Optional content ID. |
| `author_did` | TEXT | Author DID. |
| `created_at` | TEXT | ISO datetime. |
| `likes_count` | INTEGER | Updated from Jetstream `app.bsky.feed.like`. |
| `reposts_count` | INTEGER | Updated from Jetstream `app.bsky.feed.repost`. |

Indexes: `posts(created_at)`, `posts(author_did)`.

---

## Keyword filter

Defined in `filter.py`.

- **Positive**: Regex list `PSU_FOOTBALL_KEYWORDS`: identity (“We Are”, “Nittany Lions”, “Beaver Stadium”, “Happy Valley”, “PSU”, “Penn State”), coaching staff (e.g. James Franklin, Matt Campbell), players, legends, program phrases. At least one must match (case-insensitive).
- **Negative**: Regex list `PSU_NEGATIVE_KEYWORDS`: tech/noise (“Power Supply”, wattage, “Corsair”, “EVGA”, “PC Build”), other schools (“Portland State”, “Plymouth State”), etc. If any negative matches, the post is rejected.

A post is **relevant** if it matches at least one positive pattern and no negative pattern. Used by the ingester and backfill.

---

## Authority and follower boost

**Authority**

- **Specified DIDs** (in `authority_dids.py`): Get a fixed **base** `authority_multiplier` of **2.0**.
- **Others**: Start at 1.0; after **10+** posts that pass the filter in the last month, base is promoted to **1.5** (see `maybe_promote_authority` in db/ingester).

**Follower boost**

- Stored in `users.followers_count` when we have profile data (e.g. during backfill).
- `follower_boost(followers_count)` is `1.0` when unknown or 0; otherwise `1 + min(0.5, log10(1 + followers) / 10)` (cap +50%).
- **Effective multiplier** = base authority × follower boost. So listed DIDs with large followings can go above 2.0 (e.g. 2.0 × 1.5 = 3.0).

---

## Ranking (Hacker News–style score)

Implemented in `ranking.py` and used in `main.py` for the feed and dev view.

Formula:

- **P** = (likes + reposts) × effective_authority_multiplier, then subtract 1 (author’s implicit point).
- **T** = age of post in hours.
- **G** = gravity (config, default 1.5).

**Score** = max(0, P − 1) / (T + 2)^G

- Higher engagement and higher authority → higher score.
- Older posts decay; gravity controls how fast they drop.

Feed response: top N posts by this score, returned as a list of post URIs (skeleton). Bluesky hydrates them for the user.

---

## Ingester

- **Command**: `python -m psu_feed.ingester`
- Connects to Jetstream (`app.bsky.feed.post`, `app.bsky.feed.like`, `app.bsky.feed.repost`).
- For each **post** commit: if `is_relevant_post(text)`:
  - Inserts post (uri, cid, author_did, created_at).
  - If author is in `AUTHORITY_DIDS`, sets their base multiplier to 2.0; else increments match_count and may promote to 1.5×.
- For each **like** / **repost** commit: if subject URI is in `posts`, increments `likes_count` or `reposts_count`.
- Reconnects with backoff on disconnect.

---

## Backfill

- **Command**: `python -m psu_feed.backfill [options]`
- Uses `BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD`.
- **Authority**: For each DID in `authority_dids.py`, fetches author feed (paginated), applies keyword filter, inserts posts and updates user authority; when author profile is present, stores **followers_count**.
- **Search**: Runs keyword search for terms like “Penn State”, “Nittany Lions”, etc.; applies same filter; inserts posts and stores follower count when available.
- **Options**: `--authority-only`, `--search-only`, `--since`, `--until` (ISO), `--verbose`, `--authority-no-filter` (index all authority posts), `--search-max-pages` (default 20 per query to avoid unbounded run time).

Posts are inserted with `INSERT OR IGNORE`; re-running adds new posts and updates follower counts without duplicating URIs.

---

## Feed API

- **Command**: `uvicorn psu_feed.main:app --host 0.0.0.0 --port 8000`

**Endpoints**

- **GET `/xrpc/app.bsky.feed.describeFeedGenerator`**  
  Returns feed generator DID and feed list (URI, displayName, description) for discovery.

- **GET `/xrpc/app.bsky.feed.getFeedSkeleton`**  
  Query params: `feed` (required), `limit`, `cursor`.  
  Loads recent posts from DB (within lookback window), computes HN score with effective authority (including follower boost), sorts by score descending, returns top N as `{ "feed": [ { "post": uri }, ... ], "cursor"?: ... }`.

- **GET `/dev/feed`**  
  Dev-only: same ranking but hydrates post content via Bluesky API and shows a table (author, text, likes/reposts, **score**, created). Query params: `limit`, `gravity`, `lookback_hours` to tune the algorithm. Scores use **live** like/repost counts from the API so you can see non-zero scores and compare order.

---

## Publishing the feed

- **Command**: `python -m psu_feed.publish_feed`
- Requires `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`, and `FEED_SERVICE_DID` (and optionally `FEED_RKEY`, `FEED_DISPLAY_NAME`, `FEED_DESCRIPTION`).
- Creates the `app.bsky.feed.generator` record on your account. After that, the feed appears in Bluesky (e.g. Discover Feeds); the app will call your server’s `getFeedSkeleton` when users open it.

---

## Deployment (VPS)

1. Run the **ingester** as a long-lived process (e.g. systemd or Docker).
2. Run the **API** (e.g. uvicorn behind Gunicorn or similar).
3. Put the API behind **HTTPS** (Nginx/Caddy) on port 443; Bluesky requires HTTPS for feed generators.
4. Set `FEED_SERVICE_DID` to your public DID (e.g. `did:web:yourdomain.com`).
5. Run **backfill** once (or periodically) to seed/refresh posts and follower counts.
6. Run **publish_feed** once per account/feed.

---

## Quick reference

| Task | Command |
|------|--------|
| Install | `pip install -e .` |
| Run ingester | `python -m psu_feed.ingester` |
| Run API | `uvicorn psu_feed.main:app --host 0.0.0.0 --port 8000` |
| Backfill | `python -m psu_feed.backfill` |
| Publish feed | `python -m psu_feed.publish_feed` |
| Dev preview | Open `http://localhost:8000/dev/feed` |

| Tuning | Where |
|--------|--------|
| Keywords | `src/psu_feed/filter.py` |
| Authority DIDs | `src/psu_feed/authority_dids.py` |
| Gravity / lookback | Env or `config.py` |
| Follower boost cap | `ranking.py` → `FOLLOWER_BOOST_MAX` |
