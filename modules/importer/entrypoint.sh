#!/bin/sh
set -e
PORT="${PORT:-8080}"
APP_MODULE="${APP_MODULE:-apps.api.main:app}"

echo "Starting unified MuMa API: $APP_MODULE on port $PORT"
uvicorn "$APP_MODULE" --host 0.0.0.0 --port "$PORT"
