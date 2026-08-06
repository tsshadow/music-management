#!/bin/bash
# scripts/test/db-integration.sh
# Runs tests/integration/ against a throwaway MariaDB.
#
# These are the tests the unit suite cannot be: everything under services/ mocks
# the database cursor, so it proves the right SQL string is produced, not that
# MariaDB accepts it. This suite builds the real schema (db_init + every
# router's init_db + every migrate_*.sql) and runs the endpoints against it.
#
# The container matches docker/compose.test.yml's test-db: same image, same
# credentials, tmpfs storage so nothing survives the run.
#
# Usage: ./scripts/test/db-integration.sh [pytest-args...]
#        KEEP_DB=1 ./scripts/test/db-integration.sh   # leave the container up

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

CONTAINER="${DB_INTEGRATION_CONTAINER:-muma-integration-db}"
IMAGE="mariadb:10.6"
HOST_PORT="${DB_INTEGRATION_PORT:-13306}"

export DB_HOST=127.0.0.1
export DB_PORT="$HOST_PORT"
export DB_USER=muma_test
export DB_PASS=muma_test
export DB_DB=muma_test
export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/services:${PYTHONPATH:-}"
# The tagger, scanner and radio loops write on their own schedule. Against this
# database that collides with the per-test truncate: the radio scheduler holds
# radio_timeline rows while the fixture is emptying every table, and whichever
# run is slow enough for the scheduler to tick fails with lock waits.
export MUMA_DISABLE_BACKGROUND_WORKERS=1

cleanup() {
    if [ "${KEEP_DB:-0}" = "1" ]; then
        echo "--- Leaving $CONTAINER running (KEEP_DB=1) ---"
        return
    fi
    echo "--- Removing $CONTAINER ---"
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "--- Starting $IMAGE as $CONTAINER on port $HOST_PORT ---"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
    -e MYSQL_ROOT_PASSWORD=test-root-password \
    -e MYSQL_USER="$DB_USER" \
    -e MYSQL_PASSWORD="$DB_PASS" \
    -e MYSQL_DATABASE="$DB_DB" \
    -p "$HOST_PORT:3306" \
    --tmpfs /var/lib/mysql \
    "$IMAGE" >/dev/null

echo "--- Waiting for the database to accept connections ---"
for attempt in $(seq 1 60); do
    if docker exec "$CONTAINER" healthcheck.sh --connect --innodb_initialized >/dev/null 2>&1; then
        echo "Ready after ${attempt}s."
        break
    fi
    if [ "$attempt" -eq 60 ]; then
        echo "Database did not become ready in 60s. Logs:" >&2
        docker logs --tail 40 "$CONTAINER" >&2
        exit 1
    fi
    sleep 1
done

echo "--- Running tests/integration/ ---"
python3 -m pytest -p no:warnings tests/integration/ "$@"

echo "--- Database integration tests passed ---"
