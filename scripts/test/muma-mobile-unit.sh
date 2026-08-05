#!/bin/bash
# scripts/test/muma-mobile-unit.sh
# Runs Android unit tests with Jacoco coverage inside a Docker container.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "--- Running MuMa Mobile Android unit tests with coverage (via Docker) ---"

# Use a gradle home directory outside the project tree to avoid git checkout permission issues.
# Suffix it with CI_CONCURRENT_ID (unique per concurrent job slot on a runner) so that two
# MuMa Mobile jobs running at the same time never share a Gradle cache/daemon - concurrent access
# to the same GRADLE_USER_HOME causes "Timeout waiting to lock journal cache" failures. The
# workflow: rules in .gitlab-ci.yml removed the branch-pipeline/MR-pipeline duplication that first
# caused this, but two pipelines on different branches can still land on the same runner.
GRADLE_HOME_DIR="/tmp/.gradle_muma_${CI_CONCURRENT_ID:-local}"
mkdir -p "$GRADLE_HOME_DIR"

# A runner that ran the older, root-in-container version of this script still
# has a root-owned Gradle home from back then, which the container - now the
# host user - cannot write to. Hand it over once, via a throwaway root
# container, so the switch does not need a manual cleanup on every runner.
if [ -n "$(find "$GRADLE_HOME_DIR" ! -user "$(id -u)" -print -quit 2>/dev/null)" ]; then
    echo "Reclaiming $GRADLE_HOME_DIR for $(id -un)"
    docker run --rm -v "$GRADLE_HOME_DIR:/gradle_home" alpine chown -R "$(id -u):$(id -g)" /gradle_home
fi

# The container below runs as the host user, so no chmod 777 pre-step and no
# chown-back trap: nothing it writes is owned by root in the first place.
source "$ROOT_DIR/scripts/ci/android-image.sh"

docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$ROOT_DIR:/workspace" \
    -v "$GRADLE_HOME_DIR:/gradle_home" \
    -w "/workspace/services/muma-mobile" \
    -e GRADLE_USER_HOME="/gradle_home" \
    -e SIGNING_STORE_PASSWORD=dummy \
    -e SIGNING_KEY_ALIAS=dummy \
    -e SIGNING_KEY_PASSWORD=dummy \
    "$ANDROID_CI_IMAGE" \
    /bin/bash -c '. /etc/android-sdk-root && export ANDROID_SDK_ROOT && ./gradlew :app:jacocoTestReport'

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
    python3 -c "import xml.etree.ElementTree as ET; tree = ET.parse('$ROOT_DIR/$REPORT_DEST'); root = tree.getroot(); \
        c = [cnt for cnt in root.findall('counter') if cnt.get('type') == 'LINE'][0]; \
        cov = int(c.get('covered')); total = cov + int(c.get('missed')); \
        print(f'Total Jacoco Line Coverage: {100*cov/total:.2f}%')"
else
    echo "❌ ERROR: Coverage report not found at $REPORT_SRC"
    # List files to help debugging if it fails
    find services/muma-mobile -name "*.xml" | grep jacoco || true
    exit 1
fi

echo "--- MuMa Mobile unit tests passed and coverage extracted ---"
