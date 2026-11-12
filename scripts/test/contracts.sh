#!/bin/bash
# scripts/test/contracts.sh
# First LMS/OpenSubsonic contract test (Task 5).
# Starts the test stack (docker/compose.test.yml), copies the fixture track
# into the LMS music volume, runs the contract test suite, then tears down.
# Usage: ./scripts/test/contracts.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/compose.test.yml"
COMPOSE_PROJECT_NAME="muma-test${CI_JOB_ID:+-}${CI_JOB_ID:-}"

# Function to find a free port
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
    local status=$?
    # A red run says which hop failed, not why: the relay's own log lines (outbox, retries,
    # client errors) and music-manager's answers live only in the containers, which go next.
    if [ "$status" -ne 0 ]; then
        echo "--- Relay and error lines of the failed run (issue #242) ---"
        $COMPOSE logs --no-color --timestamps music-management-server music-manager 2>&1 \
            | grep -E 'MuMa outbox|Retry [0-9]|client error|lms-event|database is locked|ERROR|CRITICAL' \
            | tail -n 200 || true
    fi
    echo "--- Tearing down test stack ---"
    # --rmi local also deletes the two images compose built for this project.
    # Without it they stay behind under the job-id-scoped project name, one pair
    # per CI job forever: the runner had accumulated 2587 of them by 2026-08-15
    # and filled its 148G disk, which fails every job on the host at once with
    # "no space left on device". Only images compose named itself go -- test-db
    # declares `image: mariadb:10.6`, and an explicit tag is what `local` spares.
    $COMPOSE down -v --remove-orphans --rmi local
}
trap cleanup EXIT

echo "--- Building and starting test stack from a clean state ---"
$COMPOSE down -v --remove-orphans 2>/dev/null || true
$COMPOSE up -d --build

echo "--- Waiting for services to become healthy ---"
DEADLINE=$((SECONDS + 300))
for service in $($COMPOSE config --services); do
    while true; do
        cid=$($COMPOSE ps -q "$service")
        status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "none")
        [ "$status" = "healthy" ] && { echo "✔ $service is healthy"; break; }
        if [ "$status" = "unhealthy" ] || [ $SECONDS -ge $DEADLINE ]; then
            echo "❌ ERROR: $service did not become healthy in time (status: $status)"
            $COMPOSE logs "$service"
            exit 1
        fi
        sleep 2
    done
done

echo "--- Copying fixture track into the LMS music volume ---"
LMS_CID=$($COMPOSE ps -q music-management-server)
docker cp "$FIXTURE" "$LMS_CID":/music/ci-test-track-001.mp3

echo "--- Running contract tests ---"
cd "$ROOT_DIR"
# Pass the dynamic ports to the tests as well
export MUMA_TEST_PORT_MANAGER
export MUMA_TEST_PORT_LMS
COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME" python3 -m pytest -p no:warnings tests/contracts/ -v
