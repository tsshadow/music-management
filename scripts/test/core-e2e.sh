#!/bin/bash
# scripts/test/core-e2e.sh
# Scan to listen, end to end: start the stack, put a track in the music volume,
# scan it, ask for it over the Subsonic API the way the mobile app does, and
# scrobble it until music-manager matches the listen back to the track.
#
# Every other suite proves one component. This is the only one that proves the
# chain.
#
# It ran manually for a while on the assumption that a full stack is expensive.
# Measured, it is about 35 seconds: three containers over an empty database and
# a single fixture track, with the image build the largest part of it. So
# e2e:scan-to-listen runs on every pipeline and gates.
#
# The stack lifecycle lives in scripts/lib/e2e-stack.sh, shared with
# scripts/test/e2e-gherkin.sh, which walks the same chain written as Gherkin.
#
# Usage: ./scripts/test/core-e2e.sh
#
# What it does NOT cover, and it is worth being blunt about it: nothing here
# runs the Android app. The 6.21.0 startup crash (docs/bug-reports/029) lived
# only in an R8-minified release build, and no test on this machine can execute
# one -- the runner LXC has no /dev/kvm, so there is no emulator. Catching that
# class of bug needs the emulator step, which is the next phase and is a
# resource decision rather than a code one.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck source=scripts/lib/e2e-stack.sh
source "$ROOT_DIR/scripts/lib/e2e-stack.sh"

e2e_stack_up muma-e2e

echo "--- Running the scan-to-listen chain ---"
cd "$ROOT_DIR"
python3 -m pytest -p no:warnings tests/e2e/ -v

echo "--- Scan-to-listen chain passed ---"
