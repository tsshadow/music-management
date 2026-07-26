#!/bin/bash
# scripts/test/core-smoke.sh
# Docker smoke test (Task 3 acceptance criterion):
# starts the core test stack (docker/compose.test.yml) from a clean environment,
# waits for all healthchecks to pass, then tears everything down.
# Usage: ./scripts/test/core-smoke.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/compose.test.yml"
COMPOSE="docker compose -f $COMPOSE_FILE -p muma-test"

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
