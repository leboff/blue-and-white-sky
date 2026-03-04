# Stage 1: build frontend (SPA at /admin). Use Debian-based image so Rollup optional deps install (Alpine/musl often breaks them).
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: API + serve frontend at /admin
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

# Copy built SPA into static dir (served at /admin)
COPY --from=frontend-builder /app/frontend/dist /app/static

ENV STATIC_DIR=/app/static

CMD ["uvicorn", "psu_feed.main:app", "--host", "0.0.0.0", "--port", "8000"]
