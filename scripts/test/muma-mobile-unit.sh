#!/bin/bash
# scripts/test/muma-mobile-unit.sh
# Runs Android unit tests with Jacoco coverage inside a Docker container.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "--- Running MuMa Mobile Android unit tests with coverage (via Docker) ---"

# Gradle home (outside the project tree, to avoid git checkout permission
# issues) plus its one-off root-ownership repair - see the helper for why it
# is shared rather than per concurrent job slot.
source "$ROOT_DIR/scripts/ci/android-gradle-home.sh"

# The container below runs as the host user, so no chmod 777 pre-step and no
# chown-back trap: nothing it writes is owned by root in the first place.
source "$ROOT_DIR/scripts/ci/android-image.sh"

docker run --rm \
    --label "ci.job=${CI_JOB_ID:-local}" \
    -u "$(id -u):$(id -g)" \
    -v "$ROOT_DIR:/workspace" \
    -v "$GRADLE_HOME_DIR:/gradle_home" \
    -w "/workspace/services/muma-mobile" \
    -e GRADLE_USER_HOME="/gradle_home" \
    -e SIGNING_STORE_PASSWORD=dummy \
    -e SIGNING_KEY_ALIAS=dummy \
    -e SIGNING_KEY_PASSWORD=dummy \
    "$ANDROID_CI_IMAGE" \
    /bin/bash -c '. /etc/android-sdk-root && export ANDROID_SDK_ROOT && ./gradlew :core:voice:test :core:subsonic-api:test :app:jacocoTestReport'

# Extract and fix the report
REPORT_SRC="services/muma-mobile/app/build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml"
REPORT_DEST="cobertura-muma-mobile.xml"

if [ -f "$ROOT_DIR/$REPORT_SRC" ]; then
    echo "--- Fixing paths in $REPORT_DEST ---"
    cp "$ROOT_DIR/$REPORT_SRC" "$ROOT_DIR/$REPORT_DEST"
    # Jacoco XML: filename="org/moire/ultrasonic/SomeFile.kt"
    # Repo path: services/muma-mobile/app/src/main/kotlin/org/moire/ultrasonic/SomeFile.kt
    sed -i 's|filename="|filename="services/muma-mobile/app/src/main/kotlin/|g' "$ROOT_DIR/$REPORT_DEST"
    sed -i 's|<source>.*</source>|<source>./</source>|g' "$ROOT_DIR/$REPORT_DEST"
    
    # Print summary for GitLab coverage regex parsing
    # The floor is a ratchet, not a target: it sits just under the current figure
    # so it cannot quietly erode. Raise it as coverage climbs; never lower it to
    # make a build green. The app module only -- :core:voice runs its tests above
    # but Jacoco is wired to :app.
    python3 - "$ROOT_DIR/$REPORT_DEST" "${MOBILE_COVERAGE_MIN:-16}" <<'PY'
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
line = next(c for c in root.findall('counter') if c.get('type') == 'LINE')
covered = int(line.get('covered'))
total = covered + int(line.get('missed'))
percent = 100.0 * covered / total if total else 0.0
minimum = float(sys.argv[2])
print(f'Total Jacoco Line Coverage: {percent:.2f}%')
if percent < minimum:
    print(f'ERROR: MuMa Mobile line coverage {percent:.2f}% is under the floor of {minimum:g}%', file=sys.stderr)
    sys.exit(1)
print(f'Required line coverage of {minimum:g}% reached.')
PY
else
    echo "❌ ERROR: Coverage report not found at $REPORT_SRC"
    # List files to help debugging if it fails
    find services/muma-mobile -name "*.xml" | grep jacoco || true
    exit 1
fi

echo "--- MuMa Mobile unit tests passed and coverage extracted ---"
