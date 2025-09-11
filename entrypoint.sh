#!/bin/sh
set -e
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
command -v ffmpeg || echo "ffmpeg missing from PATH at runtime"
# Start backend
uvicorn api.server:app --host 0.0.0.0 --port 8001 &
BACK_PID=$!

# Start frontend
cd frontend
pnpm dev:docker --host 0.0.0.0 --port 5173 &
FRONT_PID=$!

# Wait for both processes
wait -n $BACK_PID $FRONT_PID
kill -TERM $BACK_PID $FRONT_PID 2>/dev/null || true
wait