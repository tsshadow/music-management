#!/bin/sh
set -e

uvicorn api.server:app --host 0.0.0.0 --port 8001 &
cd frontend
exec pnpm dev --host 0.0.0.0 --port 5173
