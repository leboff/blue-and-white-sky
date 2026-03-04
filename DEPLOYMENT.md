# Deploying PSU Feed on Proxmox

This guide walks through running the Blue and White Sky feed on a Proxmox server (or any Debian/Ubuntu VM or LXC). You’ll run the **API** (FastAPI) and **ingester** (Jetstream client) as systemd services behind HTTPS so Bluesky can use your feed.

---

## 1. Server / VM

- **Option A – New LXC (recommended):** In Proxmox, create an LXC container (e.g. Ubuntu 24.04 or Debian 12). Give it at least 512MB RAM and a few GB disk. Start the container and open a shell (or use SSH if you’ve set it up).
- **Option B – Existing VM:** Use any Debian or Ubuntu VM you already have on Proxmox.

Ensure the system is updated:

```bash
sudo apt update && sudo apt upgrade -y
```

---

## 2. Prerequisites

- **Python 3.11+**

```bash
sudo apt install -y python3 python3-venv python3-pip git
python3 --version   # should be 3.11 or higher
```

If your distro’s package is older than 3.11, use [deadsnakes](https://github.com/deadsnakes/python3.11) (Ubuntu) or build from source.

---

## 3. Clone and install

Pick a directory for the app (e.g. under a service user or `/opt`). Example with `/opt`:

```bash
sudo mkdir -p /opt
sudo git clone https://github.com/YOUR_USER/blue-and-white-sky.git /opt/blue-and-white-sky
# Or clone your own fork / private repo and adjust the path.
```

Create a dedicated user (recommended):

```bash
sudo useradd -r -s /bin/bash -d /opt/blue-and-white-sky psu-feed
sudo chown -R psu-feed:psu-feed /opt/blue-and-white-sky
```

Install the project in a venv:

```bash
cd /opt/blue-and-white-sky
sudo -u psu-feed python3 -m venv .venv
sudo -u psu-feed .venv/bin/pip install -e .
```

---

## 4. Environment and config

Create a `.env` file in the project root. The app loads it automatically.

```bash
sudo -u psu-feed cp /opt/blue-and-white-sky/.env.example /opt/blue-and-white-sky/.env 2>/dev/null || sudo -u psu-feed touch /opt/blue-and-white-sky/.env
sudo -u psu-feed nano /opt/blue-and-white-sky/.env
```

Set at least these (replace with your values):

```env
# Required for publishing the feed and for backfill
BLUESKY_HANDLE=yourhandle.bsky.social
BLUESKY_APP_PASSWORD=your-app-password

# Required for Bluesky to discover and call your feed (use your real domain)
FEED_SERVICE_DID=did:web:yourdomain.com

# Optional: LLM classification (live stream). If set, pending posts are classified every 60s.
# GEMINI_API_KEY=your-google-ai-api-key
# GEMINI_CLASSIFIER_MODEL=gemini-2.5-flash-lite

# Optional: defaults are usually fine
# DATABASE_PATH=/opt/blue-and-white-sky/data/psu_feed.db
# FEED_DISPLAY_NAME=Penn State Football
# FEED_DESCRIPTION=Penn State football: Nittany Lions, Beaver Stadium, and PSU coverage.
# PSU_FEED_GRAVITY=1.5
# PSU_FEED_LOOKBACK_HOURS=48
```

- **App password:** In Bluesky: Settings → App passwords → Create. Use that; don’t use your main password.
- **FEED_SERVICE_DID:** Must match the host Bluesky will use to call your feed (see “HTTPS and did:web” below). Use your real domain, e.g. `did:web:feeds.example.com`.

Secure the file:

```bash
chmod 600 /opt/blue-and-white-sky/.env
```

---

## 5. Data directory and first run

The app writes SQLite and `settings.json` under the directory that contains `psu_feed.db` (by default `./data` in the project root). Ensure the service user can write there:

```bash
sudo -u psu-feed mkdir -p /opt/blue-and-white-sky/data
```

Optional but recommended: run a **backfill** once to seed the DB (uses `BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD`):

```bash
cd /opt/blue-and-white-sky
sudo -u psu-feed .venv/bin/python -m psu_feed.backfill
```

You can run backfill with `--authority-only` or `--search-only`; see `python -m psu_feed.backfill --help`.

---

## 6. Systemd: API and ingester

Run the API and ingester as two long‑running services.

**API (FastAPI):**

```bash
sudo tee /etc/systemd/system/psu-feed-api.service << 'EOF'
[Unit]
Description=PSU Feed API (FastAPI)
After=network.target

[Service]
Type=simple
User=psu-feed
Group=psu-feed
WorkingDirectory=/opt/blue-and-white-sky
Environment=PATH=/opt/blue-and-white-sky/.venv/bin
ExecStart=/opt/blue-and-white-sky/.venv/bin/uvicorn psu_feed.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

**Ingester (Jetstream):**

```bash
sudo tee /etc/systemd/system/psu-feed-ingester.service << 'EOF'
[Unit]
Description=PSU Feed Ingester (Jetstream)
After=network.target

[Service]
Type=simple
User=psu-feed
Group=psu-feed
WorkingDirectory=/opt/blue-and-white-sky
Environment=PATH=/opt/blue-and-white-sky/.venv/bin
ExecStart=/opt/blue-and-white-sky/.venv/bin/python -m psu_feed.ingester
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start both:

```bash
sudo systemctl daemon-reload
sudo systemctl enable psu-feed-api psu-feed-ingester
sudo systemctl start psu-feed-api psu-feed-ingester
sudo systemctl status psu-feed-api psu-feed-ingester
```

The API is bound to `127.0.0.1:8000` so only the reverse proxy (next step) talks to it.

---

## 7. HTTPS and did:web (Bluesky requirement)

Bluesky requires the feed over **HTTPS** on port **443**. You also need a **did:web** DID so Bluesky can discover your feed.

### 7.1 Reverse proxy (Nginx example)

Install Nginx and get a TLS certificate (e.g. Let’s Encrypt):

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d feeds.yourdomain.com
```

Create a server block (replace `feeds.yourdomain.com` and paths if needed):

```bash
sudo tee /etc/nginx/sites-available/psu-feed << 'EOF'
server {
    listen 443 ssl;
    server_name feeds.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/feeds.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/feeds.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

Enable the site and reload Nginx:

```bash
sudo ln -sf /etc/nginx/sites-available/psu-feed /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 7.2 did:web

The app serves the DID document at **GET `/.well-known/did.json`**. It uses `FEED_SERVICE_DID` from `.env` and the request’s host to build the document, so with the Nginx proxy above you don’t need a separate static file.

- Bluesky will fetch `https://feeds.yourdomain.com/.well-known/did.json` to resolve the DID.
- That URL is proxied to the API, which returns a JSON document with `id: FEED_SERVICE_DID` and a `BskyFeedGenerator` service endpoint.

Set in `.env` (must match the hostname you use in the proxy):

```env
FEED_SERVICE_DID=did:web:feeds.yourdomain.com
```

---

## 8. Publish the feed to Bluesky

After the API is up and reachable over HTTPS and did:web resolves:

```bash
cd /opt/blue-and-white-sky
sudo -u psu-feed .venv/bin/python -m psu_feed.publish_feed
```

Run this once per account/feed. After that, the feed should show up in Bluesky (e.g. Discover Feeds).

---

## 9. Admin UI and dev tools

- **Admin UI (keywords and authorities):**  
  `https://feeds.yourdomain.com/admin`  
  Edit keywords, negative keywords, and authority DIDs; changes are saved to `data/settings.json` and the ingester picks them up (no restart needed).

- **Dev feed preview:**  
  `https://feeds.yourdomain.com/dev/feed`  
  Preview ranked posts and delete test posts from the DB.

If the server is exposed to the internet, restrict `/admin` (e.g. firewall, Nginx auth, or VPN). The plan does not include auth; add it if you need it.

---

## 10. Firewall (optional)

On the host or VM:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 11. Useful commands

| Task | Command |
|------|--------|
| API logs | `sudo journalctl -u psu-feed-api -f` |
| Ingester logs | `sudo journalctl -u psu-feed-ingester -f` |
| Restart API | `sudo systemctl restart psu-feed-api` |
| Restart ingester | `sudo systemctl restart psu-feed-ingester` |
| Run backfill again | `cd /opt/blue-and-white-sky && sudo -u psu-feed .venv/bin/python -m psu_feed.backfill` |
| Edit env | `sudo -u psu-feed nano /opt/blue-and-white-sky/.env` then restart services |

---

## 12. Checklist

- [ ] VM or LXC created and updated
- [ ] Python 3.11+ and venv; project installed with `pip install -e .`
- [ ] `.env` with `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`, `FEED_SERVICE_DID`
- [ ] `data/` directory exists and writable by `psu-feed`
- [ ] Optional: backfill run once
- [ ] `psu-feed-api` and `psu-feed-ingester` systemd units enabled and started
- [ ] Nginx (or Caddy) with TLS and proxy to `127.0.0.1:8000`
- [ ] `https://your-feed-host/.well-known/did.json` returns DID with `BskyFeedGenerator` service
- [ ] `publish_feed` run once
- [ ] Feed appears in Bluesky and stays updated (ingester running)

If something breaks, check `journalctl -u psu-feed-api` and `journalctl -u psu-feed-ingester` and Nginx error logs.

---

## 13. Deploying with Dokploy

You can easily deploy this project using [Dokploy](https://docs.dokploy.com/docs/core). The repository includes a `Dockerfile` and `docker-compose.yml` ready for Dokploy's Compose deployments.

1. **Create a new Compose Application:** In your Dokploy dashboard, navigate to a project and select "Create Compose".
2. **Source:** Select Git as the source and connect this repository.
3. **Environment Variables:** In the Environment tab of your application in Dokploy, provide your configuration:
   ```env
   BLUESKY_HANDLE=yourhandle.bsky.social
   BLUESKY_APP_PASSWORD=your-app-password
   FEED_SERVICE_DID=did:web:yourdomain.com
   FEED_DISPLAY_NAME=Penn State Football
   ```
4. **Deploy:** Deploy the application. Dokploy will build the images and launch both the `api` and `ingester` services. The shared data volume (`psu_feed_data`) will persist your database and settings.
5. **Domains:** Configure your domain in Dokploy to route external HTTPS traffic to the `api` service (which runs on port `8000`).
6. **Publishing the Feed:** After the services are running and your domain is accessible, open a terminal session into the `api` container through Dokploy and run:
   ```bash
   python -m psu_feed.publish_feed
   ```
