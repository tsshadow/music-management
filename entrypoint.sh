#!/bin/sh
set -e
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
command -v ffmpeg || echo "ffmpeg missing from PATH at runtime"
# Start backend only (frontend assets are pre-built)
uvicorn api.server:app --host 0.0.0.0 --port 8001
