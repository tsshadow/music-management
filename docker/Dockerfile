# Frontend build stage
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend .
RUN npm run build

# Base application image
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi
COPY scrobbler ./scrobbler
COPY analyzer ./analyzer
COPY --from=frontend /app/frontend/dist ./scrobbler/app/static

# Scrobbler API stage
FROM base AS scrobbler
ENV SCROBBLER_DB_DSN="sqlite+aiosqlite:///./data/scrobbler.db"
EXPOSE 8080
CMD ["uvicorn", "scrobbler.app.main:app", "--host", "0.0.0.0", "--port", "8080"]

# Analyzer worker stage
FROM base AS analyzer-worker
CMD ["rq", "worker", "scrobbler-analyzer"]
