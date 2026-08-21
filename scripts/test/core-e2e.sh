#!/bin/bash
# scripts/test/core-e2e.sh
# The golden path, end to end: start the stack, put a track in the music volume,
# scan it, find it over the Subsonic API the way the mobile app does, scrobble
# it, and read the listen back.
#
# Every other suite proves one component. This is the only one that proves the
# chain, which is why it exists even though it is the slowest thing here.
#
# Manual on purpose. It builds images and holds a stack for a few minutes, and
# nothing downstream gates on it, so it runs when someone asks rather than on
# every push.
#
# Usage: ./scripts/test/core-e2e.sh
#
# What it does NOT cover, and it is worth being blunt about it: nothing here
# runs the Android app. The 6.21.0 startup crash (docs/bug-reports/029) lived
# only in an R8-minified release build, and no test on this machine can execute
# one -- the runner LXC has no /dev/kvm, so there is no emulator. Catching that
# class of bug needs the emulator step, which is the next phase and is a
# resource decision rather than a code one.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/compose.test.yml"
COMPOSE_PROJECT_NAME="muma-e2e${CI_JOB_ID:+-}${CI_JOB_ID:-}"

find_free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()'
}

MUMA_TEST_PORT_MANAGER=$(find_free_port)
MUMA_TEST_PORT_LMS=$(find_free_port)
export MUMA_TEST_PORT_MANAGER
export MUMA_TEST_PORT_LMS

echo "--- Using dynamic ports: Manager=$MUMA_TEST_PORT_MANAGER, LMS=$MUMA_TEST_PORT_LMS ---"

COMPOSE="docker compose -f $COMPOSE_FILE -p $COMPOSE_PROJECT_NAME"
FIXTURE="$ROOT_DIR/tests/fixtures/music/ci-test-track-001.mp3"

cleanup() {
    echo "--- Tearing down e2e stack ---"
    # --rmi local for the same reason contracts.sh does it: without it every run
    # leaves a pair of images behind under its own project name and eventually
    # fills the runner's disk.
    $COMPOSE down -v --remove-orphans --rmi local
}
trap cleanup EXIT

echo "--- Building and starting the stack from a clean state ---"
$COMPOSE down -v --remove-orphans 2>/dev/null || true
$COMPOSE up -d --build

echo "--- Waiting for services to become healthy ---"
DEADLINE=$((SECONDS + 300))
for service in $($COMPOSE config --services); do
    while true; do
        cid=$($COMPOSE ps -q "$service")
        status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "none")
        [ "$status" = "healthy" ] && { echo "OK: $service is healthy"; break; }
        if [ "$status" = "unhealthy" ] || [ $SECONDS -ge $DEADLINE ]; then
            echo "ERROR: $service did not become healthy in time (status: $status)"
            $COMPOSE logs "$service"
            exit 1
        fi
        sleep 2
    done
done

echo "--- Copying the fixture track into the LMS music volume ---"
LMS_CID=$($COMPOSE ps -q music-management-server)
docker cp "$FIXTURE" "$LMS_CID":/music/ci-test-track-001.mp3

echo "--- Running the golden path ---"
cd "$ROOT_DIR"
COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME" python3 -m pytest -p no:warnings tests/e2e/ -v

echo "--- Golden path passed ---"
