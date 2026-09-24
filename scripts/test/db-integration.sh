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
#        MARIADB_VERSION=10.6 ./scripts/test/db-integration.sh
#
# MARIADB_VERSION defaults to what production and docker/compose.test.yml run.
# 10.6 is worth a run by hand when a change touches a TIMESTAMP column: production's
# oldest tables were created on 10.6, whose explicit_defaults_for_timestamp=OFF gave
# the first TIMESTAMP column of a table an implicit ON UPDATE CURRENT_TIMESTAMP (bug
# report 039) -- 12.3 never does, so only a 10.6 run reproduces it.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Per-job container name and port in CI, fixed ones locally. The fixed name
# was a repeat offender: two pipelines on one runner each `docker rm -f` the
# same container at start AND end of their run, so the sibling's database
# vanished mid-test ("2013 Lost connection", then "2003 Connection refused")
# while the log blamed whatever migration happened to be running. Every other
# compose-based job already isolates on CI_JOB_ID; this script was the
# straggler. Locally (no CI_JOB_ID) the old name and port 13306 stay, so
# KEEP_DB=1 inspection workflows keep working -- but a local run on a machine
# that is also a CI runner no longer kills a pipeline's database.
find_free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()'
}
CONTAINER="${DB_INTEGRATION_CONTAINER:-muma-integration-db${CI_JOB_ID:+-$CI_JOB_ID}}"
# Keep in step with docker/compose.test.yml and production. This read 10.6 for
# months after both moved to 12.3 (both are on 13.0 now), so every query was proven against a server
# nothing runs.
MARIADB_VERSION="${MARIADB_VERSION:-13.0}"
IMAGE="mariadb:${MARIADB_VERSION}"
if [ -z "${DB_INTEGRATION_PORT:-}" ] && [ -n "${CI_JOB_ID:-}" ]; then
    HOST_PORT="$(find_free_port)"
else
    HOST_PORT="${DB_INTEGRATION_PORT:-13306}"
fi

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

# tests/integration/test_schema_drift.py builds the schema from nothing twice, each
# time in a database of its own, so the test user needs more than the one database
# the image creates for it. Scoped to the muma_test_ prefix, and the container is
# throwaway either way.
docker exec "$CONTAINER" mariadb -uroot -ptest-root-password \
    -e "GRANT ALL PRIVILEGES ON \`muma\\_test\\_%\`.* TO '$DB_USER'@'%'"

echo "--- Running tests/integration/ against $IMAGE ---"
# In CI pytest runs inside the images' Python with requirements.txt installed
# (see scripts/test/music-management-unit.sh for why). The database stays a
# sibling container on this host; --network host lets the test container reach
# it on 127.0.0.1:$HOST_PORT exactly as a native run does.
# shellcheck source=scripts/lib/python-tooling.sh
source "$ROOT_DIR/scripts/lib/python-tooling.sh"
if tooling_container_required; then
    TOOLING_REQUIREMENTS="requirements.txt"
    tooling_use_ci_image
    TOOLING_DOCKER_ARGS=(--network host)
    TOOLING_ENV_VARS=(DB_HOST DB_PORT DB_USER DB_PASS DB_DB MUMA_DISABLE_BACKGROUND_WORKERS)
    echo "--- Running inside $TOOLING_IMAGE ---"
    extra_args=""
    if [ $# -gt 0 ]; then
        extra_args="$(printf '%q ' "$@")"
    fi
    tooling_container "PYTHONPATH=/repo:/repo/services python3 -m pytest -p no:warnings tests/integration/ $extra_args"
else
    python3 -m pytest -p no:warnings tests/integration/ "$@"
fi

echo "--- Database integration tests passed ---"
