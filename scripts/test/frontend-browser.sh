#!/bin/bash
# scripts/test/frontend-browser.sh
# Frontend browser test (Task 7 / Phase 5.2): starts the test stack, creates
# the admin user, imports + scans the fixture track, then runs the Playwright
# browser suite against the frontend dev server, and tears everything down.
# Usage: ./scripts/test/frontend-browser.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/compose.test.yml"
COMPOSE_PROJECT_NAME="muma-test${CI_JOB_ID:+-}${CI_JOB_ID:-}"
COMPOSE="docker compose -f $COMPOSE_FILE -p $COMPOSE_PROJECT_NAME"
FIXTURE="$ROOT_DIR/tests/fixtures/music/ci-test-track-001.mp3"
FRONTEND_DIR="$ROOT_DIR/services/frontend"

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

echo "--- Creating admin user ---"
curl -sf -X POST http://localhost:18000/api/auth/setup \
    -H "Content-Type: application/json" \
    -d '{"username":"ci-contract-admin","password":"ci-contract-password"}' >/dev/null

echo "--- Waiting for admin to sync into LMS ---"
DEADLINE=$((SECONDS + 30))
while true; do
    status=$(curl -s "http://localhost:15082/rest/ping.view?u=ci-contract-admin&p=ci-contract-password&v=1.16.1&c=test&f=json" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['subsonic-response']['status'])" 2>/dev/null || echo "")
    [ "$status" = "ok" ] && break
    [ $SECONDS -ge $DEADLINE ] && { echo "❌ ERROR: admin user did not sync into LMS in time"; exit 1; }
    sleep 1
done

echo "--- Copying fixture track and triggering a scan ---"
LMS_CID=$($COMPOSE ps -q music-management-server)
docker cp "$FIXTURE" "$LMS_CID":/music/ci-test-track-001.mp3
curl -sf -X POST "http://localhost:15082/muma/api/admin/libraries?u=ci-contract-admin&p=ci-contract-password" \
    -H "Content-Type: application/json" \
    -d '{"name":"ci-test-library","path":"/music"}' >/dev/null
curl -sf "http://localhost:15082/rest/startScan.view?u=ci-contract-admin&p=ci-contract-password&v=1.16.1&c=test&f=json" >/dev/null

echo "--- Waiting for the fixture track to be scanned ---"
DEADLINE=$((SECONDS + 60))
while true; do
    found=$(curl -s "http://localhost:15082/rest/search3.view?u=ci-contract-admin&p=ci-contract-password&v=1.16.1&c=test&f=json&query=CI%20Test%20Track" \
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
VITE_API_TARGET=http://localhost:18000 VITE_LMS_TARGET=http://localhost:15082 npx playwright test
