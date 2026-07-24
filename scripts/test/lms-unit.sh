#!/bin/bash
# scripts/test/lms-unit.sh
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
# Usage: ./scripts/test/lms-unit.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LMS_DIR="$ROOT_DIR/services/music-management-server"
IMAGE_TAG="${LMS_UNIT_IMAGE_TAG:-lms-unit-test:latest}"

echo "--- Building LMS and running its CTest/GTest suite (via Dockerfile-build-alpine) ---"
docker build -f "$LMS_DIR/Dockerfile-build-alpine" -t "$IMAGE_TAG" "$LMS_DIR"

echo "--- LMS unit tests passed (executed during the image build above) ---"
