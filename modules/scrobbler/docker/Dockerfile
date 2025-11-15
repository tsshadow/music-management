# Frontend build stage
FROM node:24-alpine AS frontend
WORKDIR /app
COPY apps/web/pnpm-lock.yaml apps/web/package.json apps/web/pnpm-workspace.yaml ./apps/web/
WORKDIR /app/apps/web
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

# Base application image
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY modules/scrobbler/pyproject.toml modules/scrobbler/README.md ./
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi
COPY modules/scrobbler/backend ./backend
COPY modules/scrobbler/analyzer ./analyzer
COPY --from=frontend /app/apps/web/build ./backend/app/static

# Backend API stage
FROM base AS backend
ENV SCROBBLER_DB_DSN="sqlite+aiosqlite:///./data/scrobbler.db"
EXPOSE 8080
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]

# Analyzer worker stage
FROM base AS analyzer-worker
CMD ["rq", "worker", "scrobbler-analyzer"]
