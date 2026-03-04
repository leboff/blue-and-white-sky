# PSU Feed — Frontend (SPA)

React + TypeScript + Vite SPA for Admin (keywords, authorities) and Dev Feed (preview, classify, delete). Built with `base: '/admin/'` so it is served at **/admin** by the same API (Dokploy/single container).

## Setup

```bash
npm install
```

## Dev (with API proxy)

Start the backend on port 8000, then:

```bash
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/admin` and `/dev` to the API. In production the app lives at **https://your-domain/admin**.

## Build

```bash
npm run build
```

Output is in `dist/`. The Dockerfile builds this and copies it into the API image; the API serves it at `/admin` and `/admin/*` (with `/admin/settings` still the JSON API).
