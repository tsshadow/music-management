#!/bin/bash
# scripts/test/muma-mobile-emulator-smoke.sh
# Boots the R8-minified release APK on an emulator and verifies the app comes
# up without crashing.
#
# Why this exists: the 6.21.0 startup crash (docs/bug-reports/029) lived only
# in the minified release build - a Gson model whose TypeToken R8 had stripped.
# Unit tests, detekt and lint all run against unminified code, so nothing in
# the pipeline could see it; the first thing that ever executed a release build
# was a user's phone, via the hoster's auto-update. This script is the earlier
# execution.
#
# What it proves and no more, for two launches (a first start and a cold
# restart after force-stop, which reads back what the first one persisted):
# the APK installs, the process is alive with no FATAL EXCEPTION or ANR after a
# grace period, CapacitorActivity is the resumed activity (the trampoline
# handed over and the Koin graph resolved in onResume), and the login page's
# server field shows the app's static server. That last value only arrives
# through a JS -> native Capacitor plugin call, which R8 can break without
# crashing anything (minify/proguard-capacitor.pro). It logs into nothing and
# taps nothing - a startup tripwire, not a UI suite.
#
# Signing: the release variant is signed with a throwaway keystore that
# build.sh generates (keystore.jks, dummy passwords below). The real signing
# key only exists on release/* pipelines, in mobile:build-release; R8 runs
# identically either way, which is all this needs.
#
# Needs /dev/kvm (runner LXC has passthrough since 2026-08-22; the udev rule
# making it 0666 is part of that setup). Fails fast with a clear message when
# it is absent rather than letting qemu die cryptically.
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR" || exit 1

if [ ! -e /dev/kvm ]; then
    echo "Error: /dev/kvm is not available on this host; the emulator cannot run." >&2
    echo "See the runner-LXC KVM passthrough notes (applied 2026-08-22)." >&2
    exit 1
fi

# The emulator writes a ~7.4GB userdata partition inside its container, so on
# the Docker data root. Without the room it dies minutes in on "FATAL | Not
# enough space to create userdata partition" (pipeline 3607, 2026-09-25,
# docs/bug-reports/073). Check first and name the fix; EMULATOR_MIN_FREE_GB
# overrides the margin (userdata plus the container's own writes).
DOCKER_ROOT_DIR="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
if [ -n "$DOCKER_ROOT_DIR" ] && command -v python3 >/dev/null 2>&1; then
    python3 "$ROOT_DIR/scripts/ci/docker_disk_preflight.py" \
        --path "$DOCKER_ROOT_DIR" \
        --min-free-gb "${EMULATOR_MIN_FREE_GB:-12}" \
        --job "mobile:smoke on $(hostname)"
fi

echo "--- Running MuMa Mobile emulator smoke test (release build) ---"

# The server the first-run screen must suggest on a fresh install (issue #192): the one the
# build was given (MUMA_SERVER_URL, read by services/muma-mobile/app/build.gradle). A build
# without it, or with the example default, suggests nothing: empty here, and the inner script
# then looks for the screen's example address. The same variable goes to the build below, so
# they cannot differ.
SMOKE_EXPECTED_SERVER="${MUMA_SERVER_URL:-}"
case "$SMOKE_EXPECTED_SERVER" in
    https://music.example.org | https://music.example.org/) SMOKE_EXPECTED_SERVER="" ;;
esac

source "$ROOT_DIR/scripts/ci/android-gradle-home.sh"
source "$ROOT_DIR/scripts/ci/android-image.sh"

# --group-add: /dev/kvm is root:kvm 0660 (or 0666 where the LXC udev rule
# applies); the container user is a bare uid with no supplementary groups, so
# without the host's kvm gid qemu cannot open the device.
#
# --ulimit nofile: THE fix that made the emulator boot at all. Docker's
# default RLIMIT_NOFILE is ~2^30; the emulator runs a close-all-fds loop up to
# that limit while holding the big QEMU lock, so the main loop and every vcpu
# "hang" from t=0 and the hang detector segfaults the process 37s in. The
# diagnosis was a gdb thread dump: one thread busy in fcntl(fd=73244162,...),
# everyone else waiting on its mutex. A sane limit turns a multi-hour loop
# into a millisecond one.
docker run --rm \
    --label "ci.job=${CI_JOB_ID:-local}" \
    -u "$(id -u):$(id -g)" \
    --group-add "$(stat -c %g /dev/kvm)" \
    --device /dev/kvm \
    --ulimit nofile=65536:65536 \
    --shm-size=2g \
    -v "$ROOT_DIR:/workspace" \
    -v "$GRADLE_HOME_DIR:/gradle_home" \
    -w "/workspace/services/muma-mobile" \
    -e GRADLE_USER_HOME="/gradle_home" \
    -e HOME=/tmp/emu-home \
    -e SIGNING_STORE_PASSWORD=dummy-ci-password \
    -e SIGNING_KEY_ALIAS=dummy-ci \
    -e SIGNING_KEY_PASSWORD=dummy-ci-password \
    -e SMOKE_EXPECTED_SERVER="$SMOKE_EXPECTED_SERVER" \
    -e MUMA_SERVER_URL \
    -e MUMA_API_URL \
    -e MUMA_OWN_DOMAIN \
    -e MUMA_GOOGLE_CLIENT_ID \
    -e MUMA_ALLOW_DEFAULTS=true \
    "$ANDROID_CI_IMAGE" \
    /bin/bash /workspace/scripts/test/muma-mobile-emulator-smoke-inner.sh

echo "--- MuMa Mobile emulator smoke test passed ---"
