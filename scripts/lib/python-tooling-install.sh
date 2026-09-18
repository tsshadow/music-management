#!/bin/bash
# scripts/lib/python-tooling-install.sh
#
# Runs *inside* the tooling container (see python-tooling.sh): installs
# requirements-dev.txt into $PYTHONUSERBASE once, and never again while that
# directory carries the `.complete` marker.
#
# The directory is a bind mount from the host, keyed on the requirements file and
# the image, so the second job on a runner -- and every job after it -- finds the
# tools already there and does not talk to PyPI at all. That is the point: on
# 2026-09-18 files.pythonhosted.org delivered 80-260 KB/s for the better part of
# an hour, and every backend:format / lint / typecheck job on both runners hit
# the ten-minute wall re-downloading the same wheels.
#
# Three jobs of one pipeline start within seconds of each other and share the
# directory, so the install runs under a lock and re-checks the marker after
# taking it: the first job installs, the other two wait and find it done. A
# partial install (killed job, broken connection) leaves no marker, so the next
# job simply runs pip again; pip is idempotent over a half-populated user base.
set -e

base="${PYTHONUSERBASE:?PYTHONUSERBASE must be set}"
mkdir -p "$base"

if [ -f "$base/.complete" ]; then
    exit 0
fi

exec 9>"$base/.lock"
flock 9
if [ -f "$base/.complete" ]; then
    exit 0
fi

echo "--- Installing requirements-dev.txt into $base ---"
pip install --user --quiet --disable-pip-version-check -r requirements-dev.txt
touch "$base/.complete"
