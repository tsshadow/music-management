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
#
# Steps 3 and 4 are polled: `docker compose up -d` returns as soon as the
# container is started, not when the app inside it is serving, and the health
# endpoint legitimately reports degraded for a few seconds while the thread
# registry fills up.
#
# Usage: ./scripts/ci/post-deploy-verify.sh [expected_version]
# Defaults to the VERSION file at the repo root. Assumes SSH is already set up
# (scripts/ci/prod-ssh-setup.sh) - or sets it up itself when run standalone.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Standalone invocation (the muma:verify job) has no agent yet; being called
# from ci-deploy.sh it already does, and re-running the setup would pointlessly
# start a second one.
if [ -z "${REMOTE_HOST}" ]; then
    # shellcheck source=scripts/ci/prod-ssh-setup.sh
    . "$SCRIPT_DIR/prod-ssh-setup.sh"
fi

EXPECTED_VERSION="${1:-}"
if [ -z "$EXPECTED_VERSION" ] && [ -f "$PROJECT_ROOT/VERSION" ]; then
    EXPECTED_VERSION="$(tr -d '[:space:]' < "$PROJECT_ROOT/VERSION")"
fi

# The health endpoint is served by the music-manager container, published on
# 8000. Probing over SSH from the host itself deliberately skips DNS and the
# reverse proxy: this job answers "did the deploy work", not "is the domain
# resolving", and those are different alarms.
HEALTH_URL="http://localhost:8000/health"
DEADLINE=$((SECONDS + 180))

remote() {
    ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "$@"
}

echo "--- Verifying container state on $REMOTE_HOST ---"

# Two separate `docker ps` calls: multiple --filter label=... on the same key
# are AND'ed by the Docker CLI, not OR'ed, so one combined filter for two
# different project names always returns nothing.
# Inspected rather than string-matched on `docker ps` output, because the
# distinction that matters is not in that output: a one-shot container with
# restart: "no" (the old soundcloud full sweep was one) exits by design, so a grep
# for "Exited" would fail every deploy that has one. Restart policy is what
# separates "finished its job" from "died".
failed=0
for project in music-management lms; do
    echo "[$project stack]"
    states="$(remote "ids=\$(docker ps -a --filter 'label=com.docker.compose.project=${project}' -q); [ -n \"\$ids\" ] && docker inspect -f '{{.Name}}|{{.HostConfig.RestartPolicy.Name}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \$ids")"
    if [ -z "$states" ]; then
        echo "  ERROR: no containers in the ${project} stack - 'up -d' did not start anything."
        failed=1
        continue
    fi
    while IFS='|' read -r name policy state health; do
        [ -z "$name" ] && continue
        echo "  ${name#/} state=${state} health=${health} restart=${policy}"
        if [ "$state" = "restarting" ]; then
            echo "    ERROR: crash loop."
            failed=1
        elif [ "$health" = "unhealthy" ]; then
            echo "    ERROR: healthcheck is failing."
            failed=1
        elif [ "$state" = "exited" ] || [ "$state" = "dead" ] || [ "$state" = "created" ]; then
            # Empty means the same as "no": docker-compose.yml declares no
            # restart policy for soundcloud-fetcher or genre-processor, and
            # Docker's default is not to restart. Failing on their exit would
            # red every deploy, which is how a gate gets ignored.
            if [ "$policy" = "no" ] || [ -z "$policy" ]; then
                echo "    (no restart policy, exiting is expected)"
            else
                echo "    ERROR: not running, and its restart policy says it should be."
                failed=1
            fi
        fi
    done <<< "$states"
done

if [ "$failed" -ne 0 ]; then
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
    sleep 5
done

echo "--- Post-deploy verification passed ---"
