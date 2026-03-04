# Stage 1: build frontend (SPA at /admin)
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --omit=dev
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
