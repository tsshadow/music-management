#!/usr/bin/env bash
#
# Builds the Svelte bundle into services/frontend/dist.
#
# Two toolchains, two hosts. The Android jobs run inside docker/Dockerfile-android-ci, which has
# the SDK and no Node at all; the frontend jobs run npm directly on the LXC, which has Node 24.
# Putting Node in the Android image would mean rebuilding it on both runners for every mobile job,
# so the bundle is built here, where Node already is, and travels to Gradle as a GitLab artifact.
#
# `node_modules/.bin/vite` on purpose, never `npm run build`: on the workstation runner an
# unrelated Qt binary sits at /usr/bin/vite and has already eaten a quarter of an hour of a
# frontend build once. Calling the local binary by path cannot resolve to it.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/services/frontend"

cd "$FRONTEND_DIR"

if [ ! -x node_modules/.bin/vite ]; then
    echo "--- Installing frontend dependencies ---"
    npm ci --no-audit --no-fund
fi

echo "--- Building the web bundle ---"
node_modules/.bin/vite build

if [ ! -f dist/index.html ]; then
    echo "vite build produced no dist/index.html" >&2
    exit 1
fi

echo "--- Bundle ready ---"
du -sh dist
