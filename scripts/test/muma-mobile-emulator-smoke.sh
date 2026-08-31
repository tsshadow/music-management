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
# What it proves and no more: the APK installs, the launcher activity starts,
# and the process is still alive with no FATAL EXCEPTION after a grace period.
# It logs into nothing and taps nothing - a startup-crash tripwire, not a UI
# suite.
#
# Needs /dev/kvm (runner LXC has passthrough since 2026-08-22; the udev rule
# making it 0666 is part of that setup). Fails fast with a clear message when
# it is absent rather than letting qemu die cryptically.
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [ ! -e /dev/kvm ]; then
    echo "Error: /dev/kvm is not available on this host; the emulator cannot run." >&2
    echo "See the runner-LXC KVM passthrough notes (applied 2026-08-22)." >&2
    exit 1
fi

echo "--- Running MuMa Mobile emulator smoke test (release build) ---"

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
    -u "$(id -u):$(id -g)" \
    --group-add "$(stat -c %g /dev/kvm)" \
    --device /dev/kvm \
    --ulimit nofile=65536:65536 \
    --shm-size=2g \
    -v "$ROOT_DIR:/workspace" \
    -v "$GRADLE_HOME_DIR:/gradle_home" \
    -w "/workspace/services/muma-mobile" \
    -e GRADLE_USER_HOME="/gradle_home" \
    -e SIGNING_STORE_PASSWORD=dummy-ci-password \
    -e SIGNING_KEY_ALIAS=dummy-ci \
    -e SIGNING_KEY_PASSWORD=dummy-ci-password \
    "$ANDROID_CI_IMAGE" \
    /bin/bash /workspace/scripts/test/muma-mobile-emulator-smoke-inner.sh

echo "--- MuMa Mobile emulator smoke test passed ---"
