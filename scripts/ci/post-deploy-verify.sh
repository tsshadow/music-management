#!/bin/bash
# scripts/ci/post-deploy-verify.sh
#
# The gate that decides whether a production deploy actually worked.
#
# What it replaces: ci-deploy.sh used to end with two `docker ps --format`
# calls whose output nobody inspected. `docker ps` exits 0 when it prints a
# restart-looping container, and it exits 0 when it prints nothing at all, so
# the deploy reported success for both. Every production incident this project
# has had since - the LMS scan crash loop, the missing system API key, the
# radio Subsonic token - looked exactly like a green deploy.
#
# What it checks, in order:
#   1. Both compose stacks have containers at all (an empty stack is the
#      failure mode a bare `docker ps` is least able to see).
#   2. No container is Restarting, Exited, Created or (unhealthy).
#   3. /health on music-manager answers 200 with status=ok, which means the
#      database is reachable and every background thread is alive.
#   4. The version /health reports is the version we just deployed.
#   5. LMS answers its Subsonic ping.
#   6. After VERIFY_SETTLE_SECONDS (default 60) the containers are sampled
#      again: step 2 must still hold, and no container may have restarted
#      since the first sample.
#
# Steps 3-5 are polled: `docker compose up -d` returns as soon as the
# container is started, not when the app inside it is serving, and the health
# endpoint legitimately reports degraded for a few seconds while the thread
# registry fills up.
#
# Step 6 exists because a single sample taken right after `up` sees every
# container "running" -- including one that will crash in twenty seconds and
# come back, over and over, with restart: unless-stopped hiding it between
# samples. Docker's RestartCount does not hide it.
#
# Usage: ./scripts/ci/post-deploy-verify.sh [expected_version]
# Defaults to the VERSION file at the repo root. Assumes SSH is already set up
# (scripts/ci/prod-ssh-setup.sh) - or sets it up itself when run standalone.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=scripts/lib/compose_profiles.sh
. "$PROJECT_ROOT/scripts/lib/compose_profiles.sh"

# Standalone invocation (the muma:verify job) has no agent yet; being called
# from ci-deploy.sh it already does, and re-running the setup would pointlessly
# start a second one.
if [ -z "${REMOTE_HOST}" ]; then
    # shellcheck source=scripts/ci/prod-ssh-setup.sh
    . "$SCRIPT_DIR/prod-ssh-setup.sh"
fi
# Called from ci-deploy.sh the agent is inherited but PROD_SSH_OPTS is not: an
# array does not survive into a child process.
if [ "${#PROD_SSH_OPTS[@]}" -eq 0 ]; then
    # shellcheck source=scripts/lib/ssh_host_keys.sh
    . "$PROJECT_ROOT/scripts/lib/ssh_host_keys.sh"
    ssh_host_key_opts_into PROD_SSH_OPTS "$REMOTE_HOST" || exit 1
fi

EXPECTED_VERSION="${1:-}"
if [ -z "$EXPECTED_VERSION" ] && [ -f "$PROJECT_ROOT/VERSION" ]; then
    EXPECTED_VERSION="$(tr -d '[:space:]' < "$PROJECT_ROOT/VERSION")"
fi

# The health endpoint is served by the music-manager container, published on
# 8000; LMS publishes its Subsonic API on LMS_SUBSONIC_PORT (default 8080).
# Probing over SSH from the host itself deliberately skips DNS and the reverse
# proxy: this job answers "did the deploy work", not "is the domain
# resolving", and those are different alarms.
HEALTH_URL="http://localhost:8000/health"
LMS_PING_URL="http://localhost:${LMS_SUBSONIC_PORT:-8080}/rest/ping.view"
DEADLINE=$((SECONDS + ${VERIFY_TIMEOUT_SECONDS:-180}))
SETTLE_SECONDS="${VERIFY_SETTLE_SECONDS:-60}"
POLL_SECONDS="${VERIFY_POLL_SECONDS:-5}"
PROJECTS="music-management lms"

# remote CMD: run CMD on the production host.
remote() {
    ssh "${PROD_SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" "$@"
}

# sample_containers: print project|name|restart-policy|state|health|restarts
# for every container of both stacks, one per line. Two separate `docker ps`
# calls: multiple --filter label=... on the same key are AND'ed by the Docker
# CLI, not OR'ed, so one combined filter for two project names returns nothing.
sample_containers() {
    local project
    for project in $PROJECTS; do
        remote "ids=\$(docker ps -a --filter 'label=com.docker.compose.project=${project}' -q); [ -z \"\$ids\" ] || docker inspect -f '${project}|{{.Name}}|{{.HostConfig.RestartPolicy.Name}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.RestartCount}}' \$ids" || true
    done
}

# check_states SAMPLE: print every container of SAMPLE with its state, and
# return non-zero when a stack is empty or any container is in a failed state.
#
# Inspected rather than string-matched on `docker ps` output, because the
# distinction that matters is not in that output: a one-shot container with
# restart: "no" (soundcloud-fetcher, genre-processor) exits by design, so a grep
# for "Exited" would fail every deploy that has one. Restart policy is what
# separates "finished its job" from "died". A health of "starting" is not a
# failure: the worker healthchecks run once a minute.
check_states() {
    local sample="$1" failed=0 project name policy state health restarts
    for project in $PROJECTS; do
        if ! printf '%s\n' "$sample" | grep -q "^${project}|"; then
            echo "  ERROR: no containers in the ${project} stack - 'up -d' did not start anything."
            failed=1
        fi
    done
    while IFS='|' read -r project name policy state health restarts; do
        [ -z "$name" ] && continue
        echo "  [${project}] ${name#/} state=${state} health=${health} restart=${policy} restarts=${restarts}"
        if [ "$state" = "restarting" ]; then
            echo "    ERROR: crash loop."
            failed=1
        elif [ "$health" = "unhealthy" ]; then
            echo "    ERROR: healthcheck is failing."
            failed=1
        elif [ "$state" = "exited" ] || [ "$state" = "dead" ] || [ "$state" = "created" ]; then
            # Empty means the same as "no": Docker's default is not to restart.
            if [ "$policy" = "no" ] || [ -z "$policy" ]; then
                echo "    (no restart policy, exiting is expected)"
            else
                echo "    ERROR: not running, and its restart policy says it should be."
                failed=1
            fi
        fi
    done <<< "$sample"
    return "$failed"
}

# check_profile_workers SAMPLE: every source worker whose compose profile the
# production env file enables (COMPOSE_PROFILES in PROD_ENV_FILE) must be in
# SAMPLE and running. Profiles decide which workers `up` starts, so a profile
# dropped from that file would otherwise just remove a worker without a red
# check (docs/deployment.md#source-workers-are-compose-profiles). The profile
# to container map is pinned against docker/docker-compose.yml by
# tests/ci/test_compose_profiles.py. Without PROD_ENV_FILE or COMPOSE_PROFILES it
# prints SKIPPED, and fails when run as the muma:deploy or muma:verify job.
PROFILE_WORKERS="soundcloud:muma-soundcloud-worker youtube:muma-youtube-worker telegram:muma-telegram-worker importer:muma-importer-worker"
check_profile_workers() {
    local sample="$1" content profiles entry profile container state failed=0 required=0
    case "${CI_JOB_NAME:-}" in muma:deploy | muma:verify) required=1 ;; esac
    if [ -z "${PROD_ENV_FILE:-}" ]; then
        echo "  SKIPPED: source worker check, PROD_ENV_FILE is not set."
        return "$required"
    fi
    if [ -f "$PROD_ENV_FILE" ]; then content="$(cat "$PROD_ENV_FILE")"; else content="$PROD_ENV_FILE"; fi
    if ! profiles="$(compose_profiles_value "$content")"; then
        echo "  SKIPPED: source worker check, COMPOSE_PROFILES is missing or empty in PROD_ENV_FILE."
        return "$required"
    fi
    for entry in $PROFILE_WORKERS; do
        profile="${entry%%:*}"
        container="${entry#*:}"
        case ",${profiles}," in *",${profile},"*) ;; *) continue ;; esac
        state="$(printf '%s\n' "$sample" | awk -F'|' -v n="/${container}" '$2 == n { print $4; exit }')"
        if [ "$state" != "running" ]; then
            echo "  ERROR: profile '${profile}' is enabled but ${container} is ${state:-missing}, not running."
            failed=1
        fi
    done
    return "$failed"
}

# restarts_increased BEFORE AFTER: print every container whose RestartCount
# grew between the two samples, and return 0 when there is at least one.
restarts_increased() {
    local before="$1" after="$2" project name policy state health restarts old grew=1
    while IFS='|' read -r project name policy state health restarts; do
        [ -z "$name" ] && continue
        old="$(printf '%s\n' "$before" | awk -F'|' -v n="$name" '$2 == n { print $6; exit }')"
        if [ -n "$old" ] && [ "${restarts:-0}" -gt "$old" ]; then
            echo "  ERROR: ${name#/} restarted $((restarts - old)) time(s) since the first sample."
            grew=0
        fi
    done <<< "$after"
    return "$grew"
}

echo "--- Verifying container state on $REMOTE_HOST ---"
FIRST_SAMPLE="$(sample_containers)"
if ! check_states "$FIRST_SAMPLE" || ! check_profile_workers "$FIRST_SAMPLE"; then
    echo "--- Post-deploy verification FAILED: container state ---"
    exit 1
fi

echo "--- Waiting for ${HEALTH_URL} to report ok (expected version: ${EXPECTED_VERSION:-any}) ---"
last_body=""
while true; do
    # curl over SSH: prod does not expose 8000 publicly and should not start.
    # `|| true` so a connection refused during startup is a retry, not a crash.
    last_body="$(remote "curl -sS --max-time 10 ${HEALTH_URL}" 2>&1 || true)"

    status="$(printf '%s' "$last_body" | sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    version="$(printf '%s' "$last_body" | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"

    if [ "$status" = "ok" ]; then
        if [ -z "$EXPECTED_VERSION" ] || [ "$version" = "$EXPECTED_VERSION" ]; then
            echo "--- Health ok, version ${version:-unknown} ---"
            break
        fi
        echo "  health ok but version is '${version}', waiting for '${EXPECTED_VERSION}' (old container still serving?)"
    else
        echo "  not ready yet: ${status:-no response}"
    fi

    if [ "$SECONDS" -ge "$DEADLINE" ]; then
        echo "--- Post-deploy verification FAILED: health check ---"
        echo "Last response from ${HEALTH_URL}:"
        printf '%s\n' "$last_body" | sed 's/^/  /'
        if [ -n "$version" ] && [ "$version" != "$EXPECTED_VERSION" ]; then
            echo "Production is serving ${version}, not the ${EXPECTED_VERSION} this pipeline deployed."
        fi
        exit 1
    fi
    sleep "$POLL_SECONDS"
done

# Without credentials ping.view answers with a Subsonic error document and a
# 4xx, which is a perfectly good answer here: the question is whether LMS still
# has a thread free to answer at all (see the healthcheck in
# services/music-management-server/docker-compose.yml). 000 (no answer) and 5xx
# are the failures.
echo "--- Waiting for LMS to answer ${LMS_PING_URL} ---"
while true; do
    code="$(remote "curl -s -o /dev/null -w '%{http_code}' --max-time 10 ${LMS_PING_URL}" 2>/dev/null || true)"
    case "$code" in
        [234][0-9][0-9])
            echo "--- LMS answered (HTTP ${code}) ---"
            break
            ;;
    esac
    echo "  LMS not answering yet (HTTP ${code:-none})"
    if [ "$SECONDS" -ge "$DEADLINE" ]; then
        echo "--- Post-deploy verification FAILED: LMS does not answer its Subsonic ping ---"
        exit 1
    fi
    sleep "$POLL_SECONDS"
done

echo "--- Re-sampling containers in ${SETTLE_SECONDS}s (catches a crash loop between samples) ---"
sleep "$SETTLE_SECONDS"
SECOND_SAMPLE="$(sample_containers)"
failed=0
check_states "$SECOND_SAMPLE" || failed=1
if restarts_increased "$FIRST_SAMPLE" "$SECOND_SAMPLE"; then
    failed=1
fi
if [ "$failed" -ne 0 ]; then
    echo "--- Post-deploy verification FAILED: containers did not stay up ---"
    exit 1
fi

echo "--- Post-deploy verification passed ---"
