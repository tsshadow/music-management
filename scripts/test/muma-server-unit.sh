#!/bin/bash
# scripts/test/muma-server-unit.sh
# Builds and runs the upstream CTest/GTest suite for the music-management-server
# (LMS) C++ code, inside the same Alpine image used for Dockerfile-build-alpine.
#
# LMS's native dependencies (in particular Wt, but also GTest/Boost/pugixml/...)
# are not packaged for Debian/Ubuntu at all, so building this natively on a
# generic Debian CI runner would require compiling the whole stack from source
# (like Dockerfile-release does for FFmpeg/Wt), which is heavy and slow. The
# existing Dockerfile-build-alpine already installs every dependency via apk
# and runs "make test" as part of its build step, so it is reused here as a
# self-contained, already-verified build+test recipe. This only requires a
# working Docker daemon on the host running this script (no native C++
# toolchain needed locally).
#
# Usage: ./scripts/test/muma-server-unit.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER_DIR="$ROOT_DIR/services/music-management-server"
IMAGE_TAG="${MUMA_SERVER_UNIT_IMAGE_TAG:-muma-server-unit-test:latest}"

echo "--- Building MuMa Server and running its CTest/GTest suite (via Dockerfile-build-alpine) ---"
docker build -f "$SERVER_DIR/Dockerfile-build-alpine" -t "$IMAGE_TAG" "$SERVER_DIR"

echo "--- Extracting coverage report ---"
# Use a temporary container to extract the coverage XML generated during the build
CONTAINER_ID=$(docker create "$IMAGE_TAG")
docker cp "$CONTAINER_ID":/tmp/lms/coverage-lms.xml "$ROOT_DIR/coverage-muma-server.xml"
docker rm "$CONTAINER_ID"

# Fix paths in Cobertura XML for GitLab visualization.
# Files inside the container were at /tmp/lms/...
# We map them to services/music-management-server/... relative to repo root.
if [ -f "$ROOT_DIR/coverage-muma-server.xml" ]; then
    echo "--- Fixing paths in coverage-muma-server.xml ---"
    sed -i 's|filename="|filename="services/music-management-server/|g' "$ROOT_DIR/coverage-muma-server.xml"
    sed -i 's|<source>.*</source>|<source>./</source>|g' "$ROOT_DIR/coverage-muma-server.xml"
fi

echo "--- MuMa Server unit tests passed and coverage extracted ---"
