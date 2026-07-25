#!/bin/bash
# scripts/test/ultrasonic-unit.sh
# Runs Android unit tests with Jacoco coverage inside a Docker container.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "--- Running Ultrasonic Android unit tests with coverage (via Docker) ---"

# Use a gradle home directory outside the project tree to avoid git checkout permission issues.
# Suffix it with CI_CONCURRENT_ID (unique per concurrent job slot on a runner) so that two
# ultrasonic jobs running at the same time (e.g. a branch pipeline and its MR pipeline for the
# same commit) never share a Gradle cache/daemon - concurrent access to the same GRADLE_USER_HOME
# causes "Timeout waiting to lock journal cache" failures.
GRADLE_HOME_DIR="/tmp/.gradle_muma_${CI_CONCURRENT_ID:-local}"
mkdir -p "$GRADLE_HOME_DIR"
# Files inside here are written by root from inside the container below, so the
# host user (running this script) generally can't chmod them itself once they
# exist - do it via a throwaway root container instead, which can.
docker run --rm -v "$GRADLE_HOME_DIR:/gradle_home" alpine chmod -R 777 /gradle_home

# Always hand the workspace back to the host user, even if the test run below
# fails - otherwise root-owned files/directories left behind by the container
# break the *next* job's `git clean`/checkout step with "Permission denied".
fix_permissions() {
    docker run --rm -v "$ROOT_DIR:/workspace" alpine chown -R "$(id -u):$(id -g)" /workspace
}
trap fix_permissions EXIT

# We use a docker image with Android SDK to avoid installing it on the runner.
# We run as root and then fix permissions for the host (see trap above).
docker run --rm \
    -v "$ROOT_DIR:/workspace" \
    -v "$GRADLE_HOME_DIR:/gradle_home" \
    -w "/workspace/services/ultrasonic" \
    -e GRADLE_USER_HOME="/gradle_home" \
    -e SIGNING_STORE_PASSWORD=dummy \
    -e SIGNING_KEY_ALIAS=dummy \
    -e SIGNING_KEY_PASSWORD=dummy \
    mobiledevops/android-sdk-image:latest \
    /bin/bash -c "export ANDROID_SDK_ROOT=\$(find /opt /usr /usr/local -name platforms -type d -print -quit 2>/dev/null | sed 's|/platforms||'); [ -z \"\$ANDROID_SDK_ROOT\" ] && export ANDROID_SDK_ROOT=/opt/android; sdkmanager --sdk_root=\$ANDROID_SDK_ROOT \"build-tools;35.0.0\" \"platforms;android-35\" \"build-tools;34.0.0\" \"platforms;android-34\" && ./gradlew :ultrasonic:jacocoTestReport"

# Extract and fix the report
REPORT_SRC="services/ultrasonic/ultrasonic/build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml"
REPORT_DEST="cobertura-ultrasonic.xml"

if [ -f "$ROOT_DIR/$REPORT_SRC" ]; then
    echo "--- Fixing paths in $REPORT_DEST ---"
    cp "$ROOT_DIR/$REPORT_SRC" "$ROOT_DIR/$REPORT_DEST"
    # Jacoco XML: filename="org/moire/ultrasonic/SomeFile.kt"
    # Repo path: services/ultrasonic/ultrasonic/src/main/kotlin/org/moire/ultrasonic/SomeFile.kt
    sed -i 's|filename="|filename="services/ultrasonic/ultrasonic/src/main/kotlin/|g' "$ROOT_DIR/$REPORT_DEST"
    sed -i 's|<source>.*</source>|<source>./</source>|g' "$ROOT_DIR/$REPORT_DEST"
    
    # Print summary for GitLab coverage regex parsing
    python3 -c "import xml.etree.ElementTree as ET; tree = ET.parse('$ROOT_DIR/$REPORT_DEST'); root = tree.getroot(); \
        c = [cnt for cnt in root.findall('counter') if cnt.get('type') == 'LINE'][0]; \
        cov = int(c.get('covered')); total = cov + int(c.get('missed')); \
        print(f'Total Jacoco Line Coverage: {100*cov/total:.2f}%')"
else
    echo "❌ ERROR: Coverage report not found at $REPORT_SRC"
    # List files to help debugging if it fails
    find services/ultrasonic -name "*.xml" | grep jacoco || true
    exit 1
fi

echo "--- Ultrasonic unit tests passed and coverage extracted ---"
