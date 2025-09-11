#!/bin/sh
set -e

# Start backend
uvicorn api.server:app --host 0.0.0.0 --port 8001 &
BACK_PID=$!

# Start frontend
cd frontend
pnpm dev:docker --host 0.0.0.0 --port 5173 &
FRONT_PID=$!

# Wait for both processes
wait $BACK_PID
wait $FRONT_PID
