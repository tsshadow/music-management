#!/bin/bash
# scripts/test/frontend-browser.sh
# Frontend browser test (Task 7 / Phase 5.2): starts the test stack, creates
# the admin user, imports + scans the fixture track, then runs the Playwright
# browser suite against the frontend dev server, and tears everything down.
# Usage: ./scripts/test/frontend-browser.sh [playwright args...]
#   e.g. ./scripts/test/frontend-browser.sh tests/browser/subsonic-signing.spec.js --project=desktop

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
# The Playwright dev server needs a dynamic port too (playwright.config.js reads
# this): it used to be hardcoded to 5174 with --strictPort, so two pipelines on
# the same runner killed each other with "localhost:5174 is already used".
MUMA_TEST_PORT_FRONTEND=$(find_free_port)
export MUMA_TEST_PORT_MANAGER
export MUMA_TEST_PORT_LMS
export MUMA_TEST_PORT_FRONTEND

echo "--- Using dynamic ports: Manager=$MUMA_TEST_PORT_MANAGER, LMS=$MUMA_TEST_PORT_LMS, Frontend=$MUMA_TEST_PORT_FRONTEND ---"

COMPOSE="docker compose -f $COMPOSE_FILE -p $COMPOSE_PROJECT_NAME"
FIXTURE="$ROOT_DIR/tests/fixtures/music/ci-test-track-001.mp3"
FRONTEND_DIR="$ROOT_DIR/services/frontend"

cleanup() {
    echo "--- Tearing down test stack ---"
    # See the same call in scripts/test/contracts.sh: --rmi local removes the
    # images compose built under this job's project name, which otherwise pile
    # up one pair per CI job until the runner disk is full.
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

echo "--- Creating admin user ---"
curl -sf -X POST "http://localhost:$MUMA_TEST_PORT_MANAGER/api/auth/setup" \
    -H "Content-Type: application/json" \
    -d '{"username":"ci-contract-admin","password":"ci-contract-password"}' >/dev/null

echo "--- Waiting for admin to sync into LMS ---"
DEADLINE=$((SECONDS + 30))
while true; do
    status=$(curl -s "http://localhost:$MUMA_TEST_PORT_LMS/rest/ping.view?u=ci-contract-admin&p=ci-contract-password&v=1.16.1&c=test&f=json" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['subsonic-response']['status'])" 2>/dev/null || echo "")
    [ "$status" = "ok" ] && break
    [ $SECONDS -ge $DEADLINE ] && { echo "❌ ERROR: admin user did not sync into LMS in time"; exit 1; }
    sleep 1
done

echo "--- Copying fixture track and triggering a scan ---"
LMS_CID=$($COMPOSE ps -q music-management-server)
docker cp "$FIXTURE" "$LMS_CID":/music/ci-test-track-001.mp3
curl -sf -X POST "http://localhost:$MUMA_TEST_PORT_LMS/muma/api/admin/libraries?u=ci-contract-admin&p=ci-contract-password" \
    -H "Content-Type: application/json" \
    -d '{"name":"ci-test-library","path":"/music"}' >/dev/null
curl -sf "http://localhost:$MUMA_TEST_PORT_LMS/rest/startScan.view?u=ci-contract-admin&p=ci-contract-password&v=1.16.1&c=test&f=json" >/dev/null

echo "--- Waiting for the fixture track to be scanned ---"
DEADLINE=$((SECONDS + 60))
while true; do
    found=$(curl -s "http://localhost:$MUMA_TEST_PORT_LMS/rest/search3.view?u=ci-contract-admin&p=ci-contract-password&v=1.16.1&c=test&f=json&query=CI%20Test%20Track" \
        | python3 -c "import json,sys; d=json.load(sys.stdin); print(bool(d['subsonic-response'].get('searchResult3',{}).get('song')))" 2>/dev/null || echo "False")
    [ "$found" = "True" ] && break
    [ $SECONDS -ge $DEADLINE ] && { echo "❌ ERROR: fixture track was not scanned in time"; exit 1; }
    sleep 2
done

echo "--- Installing frontend dependencies (exact lockfile versions) ---"
cd "$FRONTEND_DIR"
# Always run "npm ci" instead of a conditional "npm install": a plain
# "npm install" does not strictly pin to package-lock.json and can silently
# pull a newer @playwright/test off the registry if one satisfies the
# package.json semver range (e.g. "^1.61.1" -> 1.62.0). When that happens,
# the browser binaries expected by the installed package (a specific
# Chromium/"chromium-headless-shell" revision) can differ from whatever was
# previously downloaded on this machine, and the browser tests fail with
# "Executable doesn't exist at .../chromium_headless_shell-XXXX/...". "npm
# ci" always installs exactly what package-lock.json pins, so this can't
# drift between runs/build directories, and it also always starts from a
# clean node_modules instead of relying on a leftover one being "good
# enough" (see also: this is what a previous CI run actually hit).
npm ci

echo "--- Ensuring the matching Playwright browser binaries are installed ---"
# Idempotent/self-healing: downloads only if the currently installed
# @playwright/test version's expected browser revision isn't already cached
# locally (~/.cache/ms-playwright), so this is cheap on repeat runs but
# always correct even after a @playwright/test version bump.
npx playwright install chromium

echo "--- Running Playwright browser tests ---"
# Must point at the dynamic ports picked above (find_free_port), not fixed
# ones - otherwise the frontend dev server proxies to the wrong/unbound
# ports and every API call (login, search, ...) fails with ECONNREFUSED.
export VITE_API_TARGET="http://localhost:$MUMA_TEST_PORT_MANAGER"
export VITE_LMS_TARGET="http://localhost:$MUMA_TEST_PORT_LMS"

# One invocation for the functional specs and the screenshot suite
# (tests/browser/screenshots.spec.js): the production build in
# playwright.config.js's webServer is the slow part of this job, and a second
# `npx playwright test` would pay for it again.
#
# MUMA_UPDATE_SNAPSHOTS=1 rewrites the reference screenshots instead of
# comparing against them -- the way to refresh them after an intended layout
# change, since the build this suite renders is impractical on a workstation.
# The rewritten references land in the job's artifacts; see
# docs/frontend-screenshots.md for getting them back into the tree.
PLAYWRIGHT_ARGS=("$@")
if [ "${MUMA_UPDATE_SNAPSHOTS:-}" = "1" ]; then
    echo "--- MUMA_UPDATE_SNAPSHOTS=1: rewriting the reference screenshots ---"
    PLAYWRIGHT_ARGS+=(--update-snapshots)
fi

set +e
npx playwright test "${PLAYWRIGHT_ARGS[@]}"
PLAYWRIGHT_EXIT=$?
set -e
[ "$PLAYWRIGHT_EXIT" -eq 0 ] && exit 0

# A differing screenshot is a warning, not a failed job (.gitlab-ci.yml allows
# exit code 42): the diff has to be looked at, and the first run after a route
# is added has no reference yet and fails by design. Everything else -- a
# functional spec, the login in auth.setup.js, a route in the screenshot suite
# that never rendered -- stays a failure. The junit report carries each
# failure's message; only its first line is judged, because the body below it
# lists the attachments of any failed test and one of them is always called
# "screenshot".
python3 - <<'PY'
import sys
import xml.etree.ElementTree as ET

root = ET.parse("test-results/junit-browser.xml").getroot()
hard = 0
visual = 0
for case in root.iter("testcase"):
    for problem in list(case.iter("failure")) + list(case.iter("error")):
        message = problem.get("message") or ""
        # "expect(page).toHaveScreenshot(expected) failed" for a diff,
        # "A snapshot doesn't exist at ..." for a route without a reference.
        if "toHaveScreenshot" in message or "snapshot doesn't exist" in message:
            visual += 1
        else:
            hard += 1
            print(f"--- failed: {case.get('classname')} > {case.get('name')} ---")
if hard or not visual:
    print(f"--- {hard} failure(s) that are not a screenshot comparison: the job fails ---")
    sys.exit(1)
print(f"--- {visual} screenshot(s) differ from their reference; see the artifacts ---")
sys.exit(42)
PY
