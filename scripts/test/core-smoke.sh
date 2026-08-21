#!/bin/bash
# scripts/test/core-smoke.sh
# Docker smoke test (Task 3 acceptance criterion):
# starts the core test stack (docker/compose.test.yml) from a clean environment,
# waits for all healthchecks to pass, then tears everything down.
# Usage: ./scripts/test/core-smoke.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/compose.test.yml"
# Per-job project name, same as scripts/test/frontend-browser.sh. This script
# used to hardcode "-p muma-test"; that was harmless while nothing in CI ran it,
# but two pipelines on one runner would otherwise tear down each other's stack.
COMPOSE_PROJECT_NAME="muma-test${CI_JOB_ID:+-}${CI_JOB_ID:-}"

# And dynamic ports for the same reason: compose.test.yml falls back to fixed
# 18000/15082, so a sibling pipeline collides with "port is already allocated".
find_free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()'
}
MUMA_TEST_PORT_MANAGER=$(find_free_port)
MUMA_TEST_PORT_LMS=$(find_free_port)
export MUMA_TEST_PORT_MANAGER
export MUMA_TEST_PORT_LMS
echo "--- Using dynamic ports: Manager=$MUMA_TEST_PORT_MANAGER, LMS=$MUMA_TEST_PORT_LMS ---"

COMPOSE="docker compose -f $COMPOSE_FILE -p $COMPOSE_PROJECT_NAME"

cleanup() {
    echo "--- Tearing down test stack ---"
    # --rmi local: the images compose builds under this job's project name
    # otherwise pile up one set per CI job until the runner disk is full.
    $COMPOSE down -v --remove-orphans --rmi local
}
trap cleanup EXIT

echo "--- Building and starting test stack from a clean state ---"
$COMPOSE down -v --remove-orphans 2>/dev/null || true
$COMPOSE up -d --build

echo "--- Waiting for services to become healthy ---"
DEADLINE=$((SECONDS + 300))
SERVICES=$($COMPOSE config --services)

for service in $SERVICES; do
    while true; do
        cid=$($COMPOSE ps -q "$service")
        if [ -z "$cid" ]; then
            echo "❌ ERROR: container for '$service' not found"
            exit 1
        fi
        status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "none")
        if [ "$status" = "healthy" ]; then
            echo "✔ $service is healthy"
            break
        fi
        if [ "$status" = "unhealthy" ]; then
            echo "❌ ERROR: $service reported unhealthy"
            $COMPOSE logs "$service"
            exit 1
        fi
        if [ $SECONDS -ge $DEADLINE ]; then
            echo "❌ ERROR: timed out waiting for $service to become healthy (status: $status)"
            $COMPOSE logs "$service"
            exit 1
        fi
        sleep 2
    done
done

echo "--- Core smoke test passed: all services are healthy ---"
