#!/bin/sh
set -e
PORT="${PORT:-8001}"


echo "Starting entrypoint: "
echo "apps.api.main:app --host 0.0.0.0 --port $PORT"
uvicorn apps.api.main:app --host 0.0.0.0 --port "$PORT"
