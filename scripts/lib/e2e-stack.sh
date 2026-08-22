#!/bin/bash
# scripts/lib/e2e-stack.sh
#
# Brings up docker/compose.test.yml with a fixture track in the music volume,
# and tears it down again.
#
# It was extracted when two suites ran against the same stack and had to start
# it identically; only scripts/test/core-e2e.sh is left. It stays a file of its
# own because bringing the stack up and deciding what to run against it are two
# jobs, and the next thing this needs -- triggering an LMS scan so the Subsonic
# step can assert on results rather than on a status code -- belongs here rather
# than in the runner.
#
# Usage:
#
#   source "$ROOT_DIR/scripts/lib/e2e-stack.sh"
#   e2e_stack_up muma-e2e      # project-name prefix, so two runs can coexist
#   ... run tests ...
#
# e2e_stack_up exports MUMA_TEST_PORT_MANAGER, MUMA_TEST_PORT_LMS and
# COMPOSE_PROJECT_NAME, which is what the suites read to find the stack, and
# registers the teardown on EXIT. The caller does not clean up.

E2E_STACK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
E2E_STACK_COMPOSE_FILE="$E2E_STACK_ROOT/docker/compose.test.yml"
E2E_STACK_FIXTURE="$E2E_STACK_ROOT/tests/fixtures/music/ci-test-track-001.mp3"

# Picking a free port rather than a fixed one is what keeps two pipelines from
# killing each other's run; see docs/testing-inventory.md and the db:integration
# collision it is modelled on.
e2e_stack_find_free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()'
}

e2e_stack_down() {
    echo "--- Tearing down the e2e stack ---"
    # --rmi local for the same reason contracts.sh does it: without it every run
    # leaves a pair of images behind under its own project name and eventually
    # fills the runner's disk.
    $E2E_STACK_COMPOSE down -v --remove-orphans --rmi local
}

# e2e_stack_up <project-name-prefix>
e2e_stack_up() {
    local prefix="${1:?e2e_stack_up needs a compose project-name prefix}"

    # CI_JOB_ID keeps concurrent pipelines apart; the prefix keeps two suites on
    # one machine apart, which is what happens when both are run locally.
    COMPOSE_PROJECT_NAME="${prefix}${CI_JOB_ID:+-}${CI_JOB_ID:-}"
    export COMPOSE_PROJECT_NAME

    MUMA_TEST_PORT_MANAGER=$(e2e_stack_find_free_port)
    MUMA_TEST_PORT_LMS=$(e2e_stack_find_free_port)
    export MUMA_TEST_PORT_MANAGER
    export MUMA_TEST_PORT_LMS

    echo "--- Using dynamic ports: Manager=$MUMA_TEST_PORT_MANAGER, LMS=$MUMA_TEST_PORT_LMS ---"

    E2E_STACK_COMPOSE="docker compose -f $E2E_STACK_COMPOSE_FILE -p $COMPOSE_PROJECT_NAME"
    trap e2e_stack_down EXIT

    echo "--- Building and starting the stack from a clean state ---"
    $E2E_STACK_COMPOSE down -v --remove-orphans 2>/dev/null || true
    $E2E_STACK_COMPOSE up -d --build

    echo "--- Waiting for services to become healthy ---"
    local deadline=$((SECONDS + 300))
    local service cid status
    for service in $($E2E_STACK_COMPOSE config --services); do
        while true; do
            cid=$($E2E_STACK_COMPOSE ps -q "$service")
            status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "none")
            [ "$status" = "healthy" ] && { echo "OK: $service is healthy"; break; }
            if [ "$status" = "unhealthy" ] || [ $SECONDS -ge $deadline ]; then
                echo "ERROR: $service did not become healthy in time (status: $status)"
                $E2E_STACK_COMPOSE logs "$service"
                exit 1
            fi
            sleep 2
        done
    done

    # The fixture lands on the shared volume, which music-manager's scanner walks
    # on demand (/api/scanner/scan/all, which the suites call). LMS keeps a
    # separate index and is not told to rescan, so the file is on its disk
    # without being in its library -- which is why the suites only assert that
    # search3 answers, not that it finds the track. Triggering an LMS scan here
    # is the next step for that step.
    echo "--- Copying the fixture track into the LMS music volume ---"
    local lms_cid
    lms_cid=$($E2E_STACK_COMPOSE ps -q music-management-server)
    docker cp "$E2E_STACK_FIXTURE" "$lms_cid":/music/ci-test-track-001.mp3
}
