#!/bin/bash
# scripts/ci/check-release-published.sh
#
# The release:publish job, on master after a release/* or hotfix/* merge. It holds
# release:tag until everything the tag promises exists. The tag release-vX.Y.Z is what an
# installation watches (docs/designs/ops-split/): it installs the images :X.Y.Z and the APK
# package of that version, so a tag set before they exist would start a deploy that cannot
# pull them.
#
# What it checks, for the release branch head this merge brought in (the merge's second parent):
#   1. A push pipeline of that commit on the release branch ran release:build-images and
#      mobile:build-release, both successful. Merging the release MR while the branch pipeline
#      still runs cancels it; this is where that shows.
#   2. The APK package muma-mobile/<versionName>/muma-mobile-v<versionName>-<versionCode>.apk
#      exists in this project's package registry.
#
# Needs TAG_CREATION_TOKEN (read_api is enough for this script), like create-release-tags.sh.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [ -z "${TAG_CREATION_TOKEN:-}" ]; then
    echo "Error: TAG_CREATION_TOKEN CI/CD variable is not set. See docs/self-hosting.md."
    exit 1
fi

# api PATH: GET from the project API, the token in a header file, never on the command line.
api() {
    curl -sf --header @<(printf 'PRIVATE-TOKEN: %s\n' "$TAG_CREATION_TOKEN") \
        "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/$1"
}

RELEASE_SHA="$(git rev-parse "${CI_COMMIT_SHA}^2" 2>/dev/null || true)"
if [ -z "$RELEASE_SHA" ]; then
    echo "Error: ${CI_COMMIT_SHA} is not a merge commit, so there is no release branch head to check."
    exit 1
fi
echo "--- Release branch head: ${RELEASE_SHA} ---"

PIPELINE_ID="$(api "pipelines?sha=${RELEASE_SHA}&source=push&per_page=20" | python3 -c '
import json, re, sys
for p in json.load(sys.stdin):
    if re.match(r"^(release|hotfix)/", p["ref"]):
        print(p["id"])
        break
')"
if [ -z "$PIPELINE_ID" ]; then
    echo "Error: no release or hotfix branch pipeline ran for ${RELEASE_SHA}."
    exit 1
fi

missing="$(api "pipelines/${PIPELINE_ID}/jobs?per_page=100&include_retried=false" | python3 -c '
import json, sys
wanted = {"release:build-images", "mobile:build-release"}
done = {j["name"] for j in json.load(sys.stdin) if j["name"] in wanted and j["status"] == "success"}
print(" ".join(sorted(wanted - done)))
')"
if [ -n "$missing" ]; then
    echo "Error: pipeline ${PIPELINE_ID} has no successful ${missing}."
    echo "Was the release MR merged before its branch pipeline finished? The images or the APK"
    echo "for this version may not exist; do not tag. Cut the next release to publish them."
    exit 1
fi
echo "--- Pipeline ${PIPELINE_ID}: release:build-images and mobile:build-release succeeded ---"

GRADLE=services/muma-mobile/app/build.gradle
NAME="$(grep -m1 'versionName' "$GRADLE" | sed 's/.*"\(.*\)".*/\1/')"
CODE="$(grep -m1 'versionCode' "$GRADLE" | sed 's/[^0-9]*//g')"
FILE="muma-mobile-v${NAME}-${CODE}.apk"
found="$(api "packages?package_type=generic&package_name=muma-mobile&per_page=100" | python3 -c '
import json, sys
print(next((str(p["id"]) for p in json.load(sys.stdin) if p["name"] == "muma-mobile" and p["version"] == sys.argv[1]), ""))
' "$NAME")"
if [ -z "$found" ] || ! api "packages/${found}/package_files?per_page=100" | python3 -c '
import json, sys
sys.exit(0 if any(f["file_name"] == sys.argv[1] for f in json.load(sys.stdin)) else 1)
' "$FILE"; then
    echo "Error: the package muma-mobile/${NAME} has no ${FILE}."
    exit 1
fi
echo "--- Package muma-mobile/${NAME}/${FILE} exists ---"
