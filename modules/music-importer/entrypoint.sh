#!/bin/sh
set -e
PORT="${PORT:-8001}"


echo "Starting entrypoint: "
echo "api.server:app --host 0.0.0.0 --port $PORT"
uvicorn api.server:app --host 0.0.0.0 --port "$PORT"
