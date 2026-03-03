# Blue and White Sky

A custom Bluesky feed that curates Penn State football content using Jetstream ingestion, keyword filtering, user authority scoring, and Hacker News-style decay ranking.

## Setup

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -e .
   ```

2. Copy `.env.example` to `.env` and set:
   - `BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD` for publishing the feed
   - `DATABASE_PATH` (optional; defaults to `./data/psu_feed.db`)

3. Initialize the database and run the ingester (in one terminal):
   ```bash
   python -m psu_feed.ingester
   ```

4. Start the feed API (in another terminal):
   ```bash
  uvicorn psu_feed.main:app --host 0.0.0.0 --port 8000
   ```

5. Publish the feed to your account (once):
   ```bash
   python -m psu_feed.publish_feed
   ```

## Backfill (optional)

To seed the feed with historical posts so you have data to tune the algorithm:

```bash
# Same env as publish: BLUESKY_HANDLE, BLUESKY_APP_PASSWORD
python -m psu_feed.backfill
```

This fetches recent posts from each authority account in `authority_dids.py` and runs keyword search for terms like "Penn State", "Nittany Lions", etc. Matching posts are inserted (existing URIs are skipped). Options:

- `--authority-only` – only backfill from authority account feeds
- `--search-only` – only backfill from keyword search
- `--since 2025-01-01T00:00:00.000Z` / `--until 2025-12-31T23:59:59.000Z` – limit search to a time range (search only)

Run backfill before or while the ingester is running; the feed API will then have posts to rank.

## Deployment (VPS)

Run the ingester and API under systemd or in Docker, and put Nginx (or Caddy) in front for HTTPS. The feed generator must be reachable on HTTPS port 443 for Bluesky to use it.
