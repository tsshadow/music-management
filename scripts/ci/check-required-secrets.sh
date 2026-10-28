#!/bin/bash
# scripts/ci/check-required-secrets.sh
#
# Verifies that every CI/CD variable required for a production deploy of a
# release/* branch is actually configured and non-empty, BEFORE any image is
# built or any deploy is attempted.
#
# Rationale: `PROD_ENV_FILE`/`PROD_ENV_FILE_LMS` being *set at all* is already
# checked by scripts/ci/build-and-push-images.sh and scripts/ci-deploy.sh, but
# that only guards against the variable being entirely unset -- it does NOT
# guard against a specific key inside that .env content going missing or
# empty (e.g. GOOGLE_CLIENT_ID silently dropping out after an unrelated edit
# to the CI/CD variable, which is exactly what caused the "Sign in with
# Google" button to disappear from production, see CHANGELOG 0.0.5). GitLab
# itself has no concept of "this key inside a file-type variable must be
# set", so this job exists to enforce that as an explicit, visible pipeline
# step -- per AGENTS.md rule 1 ("Tests required") / rule 10 ("contract
# discipline"), a release pipeline that skips this check is not considered
# passing, even though GitLab has no built-in mechanism to require it.
#
# Required GitLab CI/CD variables (same ones deploy already needs, see
# docs/deployment.md): PROD_ENV_FILE, PROD_ENV_FILE_LMS -- plus the four
# variables that gate release jobs at the `rules:` level (DOCKERHUB_USERNAME,
# DOCKERHUB_TOKEN, APK_HOSTER_URL, SIGNING_STORE_FILE) and PROD_REMOTE_HOST, because a job gated on
# a missing variable is silently absent rather than red.

set -e

read_env_value() {
    # $1: CI/CD variable value (either file content, or a path to a file
    #     containing it, since GitLab "file" type variables inject a path).
    local var_value="$1"
    if [ -f "${var_value}" ]; then
        cat "${var_value}"
    else
        printf '%s\n' "${var_value}"
    fi
}

require_key() {
    # $1: rendered .env content, $2: key name, $3: which CI/CD variable it comes from.
    local content="$1" key="$2" source_var="$3"
    local value
    value="$(printf '%s\n' "$content" | grep -E "^${key}=" | tail -1 | cut -d'=' -f2-)"
    if [ -z "${value}" ]; then
        echo "Missing required secret: '${key}' is not set (or empty) in the '${source_var}' CI/CD variable."
        return 1
    fi
    echo "OK: '${key}' is set in '${source_var}'."
    return 0
}

require_any_key() {
    # $1: rendered .env content, $2: human description, $3: which CI/CD
    # variable it comes from, $4..: the accepted key names.
    local content="$1" description="$2" source_var="$3"
    shift 3
    local key value
    for key in "$@"; do
        value="$(printf '%s\n' "$content" | grep -E "^${key}=" | tail -1 | cut -d'=' -f2-)"
        if [ -n "${value}" ]; then
            echo "OK: ${description} is set as '${key}' in '${source_var}'."
            return 0
        fi
    done
    echo "Missing required secret: ${description} -- none of [$*] is set (or non-empty) in the '${source_var}' CI/CD variable."
    return 1
}

require_var() {
    # $1: variable name, $2: what silently disappears without it.
    local name="$1" consequence="$2"
    if [ -z "${!name:-}" ]; then
        echo "Missing required secret: CI/CD variable '${name}' is not set. Without it ${consequence}."
        return 1
    fi
    echo "OK: '${name}' is set."
    return 0
}

missing=0

# These four gate entire jobs via `rules:` in .gitlab-ci.yml
# (release:build-images requires DOCKERHUB_*, mobile:build-release
# requires APK_HOSTER_URL and SIGNING_STORE_FILE). A rules-level variable check
# does not fail when the variable is missing -- the job silently drops out of
# the pipeline, and a skipped job blocks nothing. That failure mode is exactly
# this script's reason to exist: an expired Docker Hub token would have meant
# muma:deploy restarting production on stale :latest images (caught only
# after the restart, by post-deploy-verify), and a dropped APK variable would
# have shipped a release with no new APK and nothing red anywhere. This job
# runs unconditionally on every release/hotfix branch, so the absence fails
# loudly here instead.
require_var "DOCKERHUB_USERNAME" \
    "release:build-images vanishes and muma:deploy redeploys stale images" || missing=1
require_var "DOCKERHUB_TOKEN" \
    "release:build-images vanishes and muma:deploy redeploys stale images" || missing=1
require_var "APK_HOSTER_URL" \
    "mobile:build-release vanishes and the release ships without an APK" || missing=1
require_var "SIGNING_STORE_FILE" \
    "mobile:build-release vanishes and the release ships without an APK" || missing=1
# scripts/ci/prod-ssh-setup.sh has no default production host: without this the deploy job stops
# at its first line, after the images are already built.
require_var "PROD_REMOTE_HOST" \
    "every job that connects to the production host stops before it connects" || missing=1

if [ -z "${PROD_ENV_FILE}" ]; then
    echo "Error: PROD_ENV_FILE CI/CD variable is not set. See docs/deployment.md."
    missing=1
else
    env_content="$(read_env_value "${PROD_ENV_FILE}")"
    # GOOGLE_CLIENT_ID: backend audience verification for Google Sign-In
    # (see services/music_manager/routers/user_requests.py).
    require_key "$env_content" "GOOGLE_CLIENT_ID" "PROD_ENV_FILE" || missing=1
    # The shared system API key, under either spelling: services/music_manager/
    # api_key.py reads API_KEY first and falls back to MUMA_API_KEY, and the
    # production .env happens to use the second one. Without either, the key
    # resolution fails closed and every service-to-service caller is rejected
    # -- LMS's scrobble/rating webhooks and the management UI both stop working
    # (401/403). This was invisible while the code still carried a hardcoded
    # literal fallback; removing that literal is what made it a deploy secret.
    require_any_key "$env_content" "the shared system API key" "PROD_ENV_FILE" \
        "API_KEY" "MUMA_API_KEY" || missing=1
    # The noVNC login of the firefox container (the browser whose cookies the
    # YouTube/SoundCloud workers borrow). docker/docker-compose.yml used to
    # default it to "admin", on a port bound on every interface; the default is
    # gone, so an unset value would reach the container as an empty password.
    # See docs/bug-reports/050-deploy-starts-new-code-before-migrations.md.
    require_key "$env_content" "FIREFOX_PASSWORD" "PROD_ENV_FILE" || missing=1
fi

if [ -z "${PROD_ENV_FILE_LMS}" ]; then
    echo "Error: PROD_ENV_FILE_LMS CI/CD variable is not set. See docs/deployment.md."
    missing=1
else
    env_content_lms="$(read_env_value "${PROD_ENV_FILE_LMS}")"
    # VITE_GOOGLE_CLIENT_ID: baked into the frontend bundle at build time by
    # release:build-images -- if empty, Vite dead-code-eliminates the entire
    # "Sign in with Google" button out of the production bundle.
    require_key "$env_content_lms" "VITE_GOOGLE_CLIENT_ID" "PROD_ENV_FILE_LMS" || missing=1
fi

if [ "$missing" -ne 0 ]; then
    echo ""
    echo "One or more required secrets are missing for this release. Fix the CI/CD"
    echo "variables above (Project > Settings > CI/CD > Variables) before re-running"
    echo "this pipeline -- see docs/deployment.md and .production for the values."
    exit 1
fi

echo ""
echo "--- All required secrets are present for this release ---"
