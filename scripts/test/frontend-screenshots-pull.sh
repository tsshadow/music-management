#!/bin/bash
# scripts/test/frontend-screenshots-pull.sh
# Copies the reference screenshots a frontend:e2e job produced back into the
# tree, so they can be reviewed and committed. The suite renders the production
# build on the CI runner (see tests/browser/screenshots.spec.js); this is how a
# refreshed set (MUMA_UPDATE_SNAPSHOTS=1) or a first reference for a new route
# gets from that job's artifacts into services/frontend/tests/browser/__screenshots__/.
# Usage: ./scripts/test/frontend-screenshots-pull.sh [branch | job id]
#   With a branch (default: the current one) the newest frontend:e2e job of
#   its open merge request is used, or of the branch itself when there is no
#   MR. A number is taken as a job id directly.
#
# Not `glab job artifact`: that reads the branch's own last pipeline, and
# .gitlab-ci.yml suppresses branch pipelines once a merge request is open, so
# on a feature branch it finds a cancelled pipeline from the first push, or
# nothing.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="${1:-$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)}"
SNAPSHOTS="services/frontend/tests/browser/__screenshots__"

if [[ "$TARGET" =~ ^[0-9]+$ ]]; then
    JOB_ID="$TARGET"
else
    echo "--- Looking up the newest frontend:e2e job for $TARGET ---"
    JOB_ID=$(python3 - "$TARGET" <<'PY'
import json
import subprocess
import sys


def api(path):
    return json.loads(subprocess.check_output(["glab", "api", path]))


branch = sys.argv[1]
mrs = api(f"projects/:id/merge_requests?source_branch={branch}&state=opened")
if mrs:
    pipelines = api(f"projects/:id/merge_requests/{mrs[0]['iid']}/pipelines")
else:
    pipelines = api(f"projects/:id/pipelines?ref={branch}&per_page=20")
for pipeline in pipelines:
    for job in api(f"projects/:id/pipelines/{pipeline['id']}/jobs?per_page=100"):
        if job["name"] == "frontend:e2e" and job["status"] in ("success", "failed"):
            print(job["id"])
            sys.exit(0)
sys.exit(1)
PY
    ) || { echo "❌ ERROR: no finished frontend:e2e job found for $TARGET"; exit 1; }
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "--- Downloading the artifacts of job $JOB_ID ---"
glab api "projects/:id/jobs/$JOB_ID/artifacts" > "$TMP/artifacts.zip"
unzip -q "$TMP/artifacts.zip" -d "$TMP/unpacked"

if [ ! -d "$TMP/unpacked/$SNAPSHOTS" ]; then
    echo "❌ ERROR: the artifacts hold no $SNAPSHOTS -- did the job get as far as the screenshot suite?"
    exit 1
fi

mkdir -p "$ROOT_DIR/$SNAPSHOTS"
cp -R "$TMP/unpacked/$SNAPSHOTS/." "$ROOT_DIR/$SNAPSHOTS/"

echo "--- Reference screenshots now in the tree (review before committing) ---"
git -C "$ROOT_DIR" status --short -- "$SNAPSHOTS"
