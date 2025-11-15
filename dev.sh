#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
VITE_API_BASE="${VITE_API_BASE:-http://localhost:${API_PORT}/api}"

cleanup() {
  if [[ -n "${API_PID:-}" ]] && ps -p "${API_PID}" > /dev/null 2>&1; then
    kill "${API_PID}" 2>/dev/null || true
  fi
  if [[ -n "${WEB_PID:-}" ]] && ps -p "${WEB_PID}" > /dev/null 2>&1; then
    kill "${WEB_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

(
  cd "${ROOT_DIR}/apps/api"
  python -m uvicorn apps.api.main:app --reload --host 0.0.0.0 --port "${API_PORT}"
) &
API_PID=$!

echo "API dev server started on http://localhost:${API_PORT} (PID: ${API_PID})"

echo "Starting web dev server with VITE_API_BASE=${VITE_API_BASE}"
(
  cd "${ROOT_DIR}/apps/web"
  VITE_API_BASE="${VITE_API_BASE}" npm run dev -- --host --port "${WEB_PORT}"
) &
WEB_PID=$!

echo "Web dev server started on http://localhost:${WEB_PORT} (PID: ${WEB_PID})"

echo "Press Ctrl+C to stop both services."

wait "${API_PID}" "${WEB_PID}"
