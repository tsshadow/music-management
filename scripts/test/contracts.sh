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
COMPOSE="docker compose -f $COMPOSE_FILE -p $COMPOSE_PROJECT_NAME"
FIXTURE="$ROOT_DIR/tests/fixtures/music/ci-test-track-001.mp3"

cleanup() {
    echo "--- Tearing down test stack ---"
    $COMPOSE down -v --remove-orphans
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
COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME" python3 -m pytest -p no:warnings tests/contracts/ -v
