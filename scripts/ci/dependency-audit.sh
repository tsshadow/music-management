#!/bin/bash
# scripts/ci/dependency-audit.sh
# Checks dependencies against the published vulnerability databases: pip-audit
# for Python, `npm audit` for the frontend, trivy for the Android dependency
# graph (via a CycloneDX SBOM) and for the OS packages inside the published
# production images.
#
# The Python side audits the *installed* environment. pip-audit's requirements
# mode resolves each file in a throwaway virtualenv, which means building every
# pin from source when no wheel matches -- numpy on a slim image is enough to
# make that fail for reasons that have nothing to do with security. The
# installed environment is also what actually runs, so a finding there is never
# theoretical. Fix one by bumping the pin in the requirements file and
# reinstalling.
#
# This is why the CI job is reporting rather than gating: the result reflects
# the environment it runs in, which this repository does not manage.
#
# Consciously accepted findings live in security/accepted-vulnerabilities.txt,
# one advisory ID per line with a reason. Everything else fails this job.
#
# Exit codes:
#   0  clean (or only accepted findings)
#   1  vulnerabilities found, or a scanner that had everything it needs broke
#   2  a scanner could not run because this environment does not have it
#
# The difference between 1 and 2 is deliberate. Exit 2 means a tool or a CI
# variable is simply absent -- that is the normal outcome of running this
# locally, where docker or PROD_ENV_FILE may be missing, and it says nothing
# about the code. A scanner that had its tool and its input and still produced
# nothing is a broken audit, and a broken audit must not read as a quiet skip:
# the section scanned zero packages, so passing it would mean "not checked"
# rather than "clean". Those go in BROKEN below and exit 1.
#
# Usage: ./scripts/ci/dependency-audit.sh [--strict]
#   --strict  also fail on moderate npm findings (default: high and above)

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# shellcheck source=scripts/lib/python-tooling.sh
source "$ROOT_DIR/scripts/lib/python-tooling.sh"

ACCEPTED_FILE="security/accepted-vulnerabilities.txt"
NPM_LEVEL=high
if [ "${1:-}" = "--strict" ]; then
    NPM_LEVEL=moderate
fi

REQUIREMENTS=(
    requirements.txt
    requirements-dev.txt
    services/music_manager/requirements.txt
    services/music_manager/artist_image_fetcher/requirements.txt
    # services/ml-analyzer/requirements.txt is left out on purpose: the service is
    # deprecated, not built and not deployed (services/ml-analyzer/DEPRECATED.md), so a
    # finding there would be a red audit about code that runs nowhere.
)

STATUS=0
SKIPPED=0
# Sections that should have produced a result and did not. Reported by name and
# fatal; see the exit-code note at the top of this file.
BROKEN=()

# Advisory IDs from the accepted list, as repeated --ignore-vuln arguments.
IGNORE_ARGS=()
ACCEPTED_COUNT=0
if [ -f "$ACCEPTED_FILE" ]; then
    while read -r advisory; do
        [ -n "$advisory" ] || continue
        IGNORE_ARGS+=(--ignore-vuln "$advisory")
        ACCEPTED_COUNT=$((ACCEPTED_COUNT + 1))
    done < <(sed 's/#.*//' "$ACCEPTED_FILE" | tr -d '[:blank:]' | grep -v '^$')
    echo "Accepted findings (see $ACCEPTED_FILE): $ACCEPTED_COUNT advisories"
fi

echo
echo "=== Python dependencies (pip-audit, declared requirements) ==="
for req in "${REQUIREMENTS[@]}"; do
    [ -f "$req" ] || continue
    echo "--- $req ---"
    run_python_tool pip-audit --requirement "$req" --no-deps --progress-spinner off \
                    "${IGNORE_ARGS[@]+"${IGNORE_ARGS[@]}"}"
    case $? in
        0) ;;
        127) SKIPPED=1 ;;
        *) STATUS=1 ;;
    esac
done

echo
echo "=== Frontend dependencies (npm audit, level: $NPM_LEVEL) ==="
if command -v npm >/dev/null 2>&1 && [ -f services/frontend/package-lock.json ]; then
    if ! (cd services/frontend && npm audit --audit-level="$NPM_LEVEL"); then
        STATUS=1
    fi
else
    echo "npm or services/frontend/package-lock.json missing, skipping"
    SKIPPED=1
fi

# Shared plumbing for the two trivy sections below. The vulnerability DB and
# pulled layers land in a named volume so a weekly schedule does not re-download
# ~50MB of advisory data (and image layers) every run.
TRIVY_IMAGE="aquasec/trivy:latest"
TRIVY_IGNORE="security/trivyignore"
run_trivy() {
    docker run --rm \
        -v muma-trivy-cache:/root/.cache/trivy \
        -v "$ROOT_DIR:/repo" -w /repo \
        "$TRIVY_IMAGE" "$@"
}

echo
echo "=== Android dependencies (CycloneDX SBOM + trivy) ==="
# Gradle has no lockfiles in this repo, so nothing on disk states the resolved
# dependency graph -- pip-audit and npm audit both read one, and the Android
# half of the codebase had no CVE coverage at all. The cyclonedx plugin (root
# build.gradle of muma-mobile) writes the resolved graph as an SBOM; trivy
# scans that. Renovate keeps the versions moving, but Renovate answers "is
# there something newer", not "is what I run vulnerable".
#
# Plugin 3.x writes the merged graph to build/reports/cyclonedx/ (the
# per-module halves land in each module's build/reports/cyclonedx-direct/),
# where 2.x wrote build/reports/bom.json.
SBOM="services/muma-mobile/build/reports/cyclonedx/bom.json"
# How many components trivy has to see before this section counts as a scan.
# Not a taste threshold: it separates "scanned the APK's dependency graph" from
# "scanned a file that happens to be valid CycloneDX". The graph is in the
# hundreds; a build.gradle mistake that resolves nothing yields the handful of
# project components and would otherwise pass green.
SBOM_MIN_COMPONENTS=50
if command -v docker >/dev/null 2>&1; then
    # Kept out of the log on success -- a Gradle run is thousands of lines --
    # but shown when it fails, because this now fails the audit and a failure
    # with no output is not something anyone can act on.
    SBOM_LOG="$(mktemp)"
    if ./scripts/test/muma-mobile-detekt.sh cyclonedxBom >"$SBOM_LOG" 2>&1 && [ -f "$SBOM" ]; then
        if command -v python3 >/dev/null 2>&1; then
            COMPONENTS="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("components") or []))' \
                          "$SBOM" 2>/dev/null)"
        else
            COMPONENTS="$(grep -c '"purl"' "$SBOM")"
        fi
        echo "SBOM $SBOM lists ${COMPONENTS:-0} components"
        if [ "${COMPONENTS:-0}" -lt "$SBOM_MIN_COMPONENTS" ]; then
            echo "Fewer than $SBOM_MIN_COMPONENTS components: the SBOM was written but resolved"
            echo "next to nothing, so scanning it would prove nothing. Check the"
            echo "includeConfigs block in services/muma-mobile/build.gradle against the"
            echo "configuration names the modules actually have."
            BROKEN+=("Android SBOM (empty dependency graph)")
        elif ! run_trivy sbom "$SBOM" \
            --severity HIGH,CRITICAL --exit-code 1 --ignorefile "$TRIVY_IGNORE"; then
            STATUS=1
        fi
    else
        echo "SBOM generation failed (./scripts/test/muma-mobile-detekt.sh cyclonedxBom):"
        tail -40 "$SBOM_LOG"
        BROKEN+=("Android SBOM (cyclonedxBom)")
    fi
    rm -f "$SBOM_LOG"
else
    echo "docker missing, skipping"
    SKIPPED=1
fi

echo
echo "=== Production images (trivy, OS packages + bundled libraries) ==="
# The requirements/lockfile scans above cover what the repo declares; the
# images production actually runs also contain a Debian/Alpine userland that
# nothing scanned. Resolves the same image names deploy uses from the
# PROD_ENV_FILE CI/CD variables, so this section runs in CI (schedule/master)
# and silently skips locally where those variables do not exist.
# --ignore-unfixed: a base-image CVE without an upstream fix is not actionable
# from this repo and would leave the section permanently red.
read_env_file_value() {
    # $1: variable content or path (GitLab file-type variables inject a path),
    # $2: key.
    local content
    if [ -f "${1}" ]; then content="$(cat "${1}")"; else content="${1}"; fi
    printf '%s\n' "$content" | grep -E "^${2}=" | tail -1 | cut -d'=' -f2-
}
if command -v docker >/dev/null 2>&1 && [ -n "${PROD_ENV_FILE:-}" ]; then
    DOCKER_USER="$(read_env_file_value "$PROD_ENV_FILE" DOCKER_USER)"
    IMAGE_CORE="$(read_env_file_value "$PROD_ENV_FILE" IMAGE_CORE)"
    LMS_IMAGE="$(read_env_file_value "${PROD_ENV_FILE_LMS:-}" IMAGE_NAME)"
    IMAGES=(
        "${DOCKER_USER}/${IMAGE_CORE:-music-manager}:latest"
        "${DOCKER_USER}/muma-base:latest"
        "${DOCKER_USER}/muma-downloader:latest"
        "${DOCKER_USER}/muma-telegram:latest"
        "${DOCKER_USER}/muma-importer:latest"
        "${DOCKER_USER}/muma-tools:latest"
    )
    [ -n "$LMS_IMAGE" ] && IMAGES+=("${LMS_IMAGE}:latest")
    # --scanners vuln: trivy's secret scanner flagged the self-signed *test*
    # certificate that muma-mobile's integration tests ship (the tools image
    # copies all of services/), which is exactly the kind of noise that gets a
    # report ignored. Committed secrets are gitleaks' job (security:secret-scan).
    for image in "${IMAGES[@]}"; do
        echo "--- $image ---"
        if ! run_trivy image "$image" \
            --scanners vuln \
            --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 \
            --ignorefile "$TRIVY_IGNORE"; then
            STATUS=1
        fi
    done
else
    echo "docker or PROD_ENV_FILE missing, skipping (CI-only section)"
    SKIPPED=1
fi

if [ "${#BROKEN[@]}" -ne 0 ]; then
    echo
    echo "A scanner had everything it needed and still produced no result:"
    printf '  - %s\n' "${BROKEN[@]}"
    echo "Fix the section itself. It is failed rather than skipped on purpose:"
    echo "a section that scans nothing must not be able to report clean."
fi

if [ "$STATUS" -ne 0 ]; then
    echo
    echo "Vulnerable dependencies found."
    echo "Fix: bump the pin in the requirements file / package.json the finding names."
    echo "Only if that is genuinely not possible yet, add the advisory ID to"
    echo "$ACCEPTED_FILE with a reason and a way out."
fi

if [ "$STATUS" -ne 0 ] || [ "${#BROKEN[@]}" -ne 0 ]; then
    exit 1
fi

if [ "$SKIPPED" -ne 0 ]; then
    echo
    echo "One or more scanners could not run."
    exit 2
fi

echo
echo "No unaccepted vulnerabilities at or above the configured level."
