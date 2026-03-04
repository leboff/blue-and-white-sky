# PSU Feed — Frontend (SPA)

React + TypeScript + Vite SPA that consumes the headless API for Admin (keywords, authorities) and Dev Feed (preview, classify, delete).

## Setup

```bash
npm install
```

## Dev (with API proxy)

Start the backend on port 8000, then:

```bash
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/admin` and `/dev` to the API.

## Build

```bash
npm run build
```

Output is in `dist/`. Serve it with any static host or mount under the FastAPI app.
