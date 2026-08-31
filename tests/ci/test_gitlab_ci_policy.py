"""The pipeline policy, as executable assertions.

Every rule here exists because breaking it has a concrete production
consequence, named in the test's docstring. See
docs/superpowers/plans/2026-08-02-ci-release-hardening.md.
"""

import re

from tests.ci.conftest import REPO_ROOT, job_names, load_ci


def first_condition(ci, job):
    """The job's first real `if:` rule.

    Not `rules[0]`: every job now opens with a `!reference` to
    .dedicated_schedule_guard, which parses as the reference path rather than a
    mapping. These assertions are about which branches a job runs on, so they
    should find that condition wherever it sits.
    """
    for rule in ci[job]["rules"]:
        if isinstance(rule, dict) and "if" in rule:
            return rule["if"]
    raise AssertionError(f"{job} has no `if:` rule")


def test_ci_file_parses():
    ci = load_ci()
    assert "stages" in ci
    assert job_names(ci), "no jobs found in .gitlab-ci.yml"


def test_no_job_declares_an_image():
    """The runner is a shell executor. A job with `image:` never starts."""
    ci = load_ci()
    offenders = [name for name in job_names(ci) if "image" in ci[name]]
    assert offenders == [], f"shell-executor runner cannot honour image: on {offenders}"


# Jobs that gate a production deploy. If one of these does not run on a
# release branch, deploy:prod ships code this pipeline never tested.
GATING_JOBS = [
    "quality:lint",
    "quality:typecheck",
    "music-management:unit",
    "muma-server:unit",
    "frontend:unit",
    "muma-mobile:check",
    "muma-mobile:smoke-release",
]


def test_gating_jobs_always_run_on_a_release_branch():
    """A `changes:`-only rule skips these on the stabilize commit, which
    touches nothing but VERSION/CHANGELOG/RELEASE_NOTES -- and a skipped job
    does not block deploy:prod."""
    ci = load_ci()
    for name in GATING_JOBS:
        rules = ci[name]["rules"]
        assert any(
            rule == [".release_rule", "rules"] for rule in rules
        ), f"{name} does not reference .release_rule, so it can be skipped on a release branch"


# A dedicated schedule sets exactly one of these, and exists to run exactly one
# job. Everything else must step aside.
SCHEDULE_OWNED_JOBS = {
    "deps:renovate": "$RENOVATE",
    "images:refresh-downloader": "$REFRESH_DOWNLOADER",
}

GUARD = [".dedicated_schedule_guard", "rules"]


def test_a_dedicated_schedule_does_not_drag_in_the_whole_pipeline():
    """GitLab treats `changes:` as always true in a scheduled pipeline, so every
    job whose rule is a `changes:` list matches unconditionally there. Before
    this guard, the weekly downloader refresh ran the entire suite on master --
    including release:tag and release:back-merge-develop, which both succeeded
    on pipeline 1119 for no reason anyone asked for."""
    ci = load_ci()
    offenders = [
        name
        for name in job_names(ci)
        if name not in SCHEDULE_OWNED_JOBS and GUARD not in ci[name].get("rules", [])
    ]
    assert offenders == [], (
        "these jobs would run on every dedicated schedule: " f"{offenders}"
    )


def test_the_guard_is_the_first_rule():
    """Rules are evaluated in order and the first match wins. A guard placed
    after a `changes:` rule never gets the chance to say no."""
    ci = load_ci()
    misplaced = [
        name
        for name in job_names(ci)
        if name not in SCHEDULE_OWNED_JOBS and ci[name].get("rules", [None])[0] != GUARD
    ]
    assert misplaced == [], f"guard is not the first rule on: {misplaced}"


def test_the_job_a_schedule_exists_for_is_not_guarded():
    """The inverse, and the one that actually breaks the feature: guarding
    deps:renovate would mean the renovate schedule runs nothing at all."""
    ci = load_ci()
    for name, variable in SCHEDULE_OWNED_JOBS.items():
        assert GUARD not in ci[name]["rules"], f"{name} must not step aside for its own schedule"
        conditions = " ".join(
            rule.get("if", "") for rule in ci[name]["rules"] if isinstance(rule, dict)
        )
        assert variable in conditions, f"{name} does not check {variable}"


def test_the_guard_covers_every_schedule_variable():
    """A new dedicated schedule whose variable is missing here silently gets the
    old behaviour: one job asked for, the whole suite delivered."""
    ci = load_ci()
    condition = ci[".dedicated_schedule_guard"]["rules"][0]["if"]
    for variable in SCHEDULE_OWNED_JOBS.values():
        assert variable in condition, f"{variable} is not in the guard"
    assert ci[".dedicated_schedule_guard"]["rules"][0]["when"] == "never"


def test_release_rule_covers_release_and_hotfix():
    ci = load_ci()
    condition = ci[".release_rule"]["rules"][0]["if"]
    assert "release" in condition and "hotfix" in condition


def test_deploy_prod_is_serialised():
    """Without a resource_group two pipelines deploy over each other -- see
    docs/bug-reports/016-stale-release-branch-clobbered-latest-deploy.md."""
    ci = load_ci()
    assert ci["deploy:prod"]["resource_group"] == "production"


def test_deploy_prod_declares_its_environment():
    """Gives GitLab a deployment history, so "what is live" is answerable
    without SSHing to the host."""
    ci = load_ci()
    environment = ci["deploy:prod"]["environment"]
    assert environment["name"] == "production"
    assert environment["url"] == "$PROD_URL"


def test_workflow_rules_prevent_duplicate_pipelines():
    """Jobs with `changes:`-only rules also match merge_request_event, so a
    push to a branch with an open MR runs the whole suite twice."""
    ci = load_ci()
    rules = ci["workflow"]["rules"]
    duplicate_guard = [
        rule
        for rule in rules
        if rule.get("when") == "never" and "$CI_OPEN_MERGE_REQUESTS" in rule.get("if", "")
    ]
    assert duplicate_guard, "no rule dropping the branch pipeline when an MR is open"


def test_release_branches_do_not_get_a_merge_request_pipeline():
    """The push-vs-MR dedupe keys on $CI_OPEN_MERGE_REQUESTS, which only exists
    in push pipelines -- so a release branch with an open MR got a branch
    pipeline AND an MR pipeline, ran everything twice, and the two Android jobs
    raced each other for the shared Gradle home. The branch pipeline is where
    deploy:prod lives, so the MR pipeline is the one that must never start."""
    ci = load_ci()
    rules = ci["workflow"]["rules"]
    guard = [
        rule
        for rule in rules
        if rule.get("when") == "never"
        and "$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME" in rule.get("if", "")
        and "release" in rule.get("if", "")
        and "hotfix" in rule.get("if", "")
    ]
    assert guard, "no rule suppressing the MR pipeline for release/hotfix source branches"


def test_workflow_never_suppresses_a_release_branch_pipeline():
    """deploy:prod matches on $CI_COMMIT_BRANCH, which is unset in a merge
    request pipeline. If the duplicate-pipeline guard fired for a release
    branch that happens to have an MR open, the branch pipeline would vanish
    and production would never be deployed at all. The release rule therefore
    has to be decided before the guard is reached."""
    ci = load_ci()
    rules = ci["workflow"]["rules"]
    for rule in rules:
        condition = rule.get("if", "")
        if "release" in condition and "hotfix" in condition:
            assert rule.get("when") != "never"
            break
        assert rule.get("when") != "never", (
            "a `when: never` rule is evaluated before release/hotfix branches "
            "are allowed through"
        )
    else:
        raise AssertionError("no workflow rule admits release/hotfix branches")


# Retrying a failing script would hide flakes; these are infrastructure
# failures only, where the code under test never got a fair run.
INFRA_FAILURES = {"runner_system_failure", "stuck_or_timeout_failure"}


def test_every_job_has_a_timeout():
    """A hung container otherwise holds the runner until the project timeout."""
    ci = load_ci()
    missing = [name for name in job_names(ci) if "timeout" not in ci[name]]
    assert missing == [], f"jobs without an explicit timeout: {missing}"


def test_retries_are_limited_to_infrastructure_failures():
    ci = load_ci()
    for name in job_names(ci):
        retry = ci[name].get("retry")
        if retry is None:
            continue
        # `retry: !reference [.infra_retry, retry]` parses as the reference path.
        if retry == [".infra_retry", "retry"]:
            continue
        assert set(retry["when"]) <= INFRA_FAILURES, f"{name} retries real failures"


def test_the_infra_retry_template_only_covers_infrastructure_failures():
    ci = load_ci()
    assert set(ci[".infra_retry"]["retry"]["when"]) <= INFRA_FAILURES


def test_deploy_prod_is_never_retried():
    """A half-applied deploy must be looked at, not repeated."""
    ci = load_ci()
    assert "retry" not in ci["deploy:prod"]


def test_secret_scanning_runs_on_release_branches():
    """A leaked key must not first become public in a tagged release."""
    ci = load_ci()
    job = ci["security:secret-scan"]
    assert job["stage"] == "quality"
    assert any(rule == [".release_rule", "rules"] for rule in job["rules"])


def test_test_jobs_publish_junit():
    """Without this, a failed test is only visible by reading the raw log."""
    ci = load_ci()
    for name, path in [
        ("music-management:unit", "report-python.xml"),
        # Every module, not just app/: a glob pinned to one module means a new module's
        # tests report green by publishing nothing at all.
        ("muma-mobile:check", "services/muma-mobile/**/build/test-results/**/TEST-*.xml"),
        # Kept in lockstep with playwright.config.js's junit reporter outputFile.
        ("frontend:browser", "services/frontend/test-results/junit-browser.xml"),
    ]:
        assert ci[name]["artifacts"]["reports"]["junit"] == path


def test_junit_artifacts_are_uploaded_even_when_the_job_fails():
    """A report that only appears on success is exactly backwards."""
    ci = load_ci()
    for name in ["music-management:unit", "muma-mobile:check", "frontend:browser"]:
        assert ci[name]["artifacts"]["when"] == "always"


def test_secret_scanning_is_not_allowed_to_fail():
    """Unlike the dependency audit it needs no third-party service, so a
    failure here is a finding rather than an outage."""
    ci = load_ci()
    assert ci["security:secret-scan"].get("allow_failure") is not True


# Every job that must behave identically for a hotfix and for a release.
RELEASE_STAGE_JOBS = [
    "release:check-secrets",
    "release:version-check",
    "release:build-images",
    "muma-mobile:build-release",
    "deploy:prod",
]


def test_hotfix_branches_get_the_full_release_treatment():
    """A hotfix that skips the secret check or the version check is a hotfix
    that deploys unverified straight to production."""
    ci = load_ci()
    for name in RELEASE_STAGE_JOBS:
        conditions = " ".join(
            rule.get("if", "") for rule in ci[name]["rules"] if isinstance(rule, dict)
        )
        assert "hotfix" in conditions, f"{name} does not run on a hotfix branch"


def test_release_apk_waits_for_the_android_unit_tests():
    """`needs:` bypasses stage ordering, and the muma-mobile resource group
    only serializes jobs, it does not order them. With version-check as the
    only need, muma-mobile:build-release built and UPLOADED a signed APK while
    muma-mobile:check on the same commit failed -- phones auto-update from the
    hoster, so users got untested code even though deploy:prod correctly never
    ran."""
    ci = load_ci()
    targets = [
        n["job"] if isinstance(n, dict) else n
        for n in ci["muma-mobile:build-release"]["needs"]
    ]
    assert "muma-mobile:check" in targets
    assert "release:version-check" in targets
    # And the emulator smoke test: a release APK that crashes on startup must
    # never reach the hoster (docs/bug-reports/029 shipped exactly that way).
    assert "muma-mobile:smoke-release" in targets


def test_publishing_jobs_are_not_interruptible():
    """`default: interruptible: true` lets a newer push cancel a running job.
    Fine for tests; not for anything that publishes or mutates the outside
    world halfway through."""
    ci = load_ci()
    for name in [
        "release:build-images",
        "muma-mobile:build-release",
        "deploy:prod",
        "release:tag",
    ]:
        assert ci[name].get("interruptible") is False, f"{name} can be cancelled mid-publish"


def test_rule_gating_variables_are_verified_by_the_secret_check():
    """A `rules:` condition like `&& $DOCKERHUB_TOKEN` does not fail when the
    variable is missing -- the job silently drops out of the pipeline, and a
    skipped job blocks nothing. Every variable used that way on a release
    branch must therefore be asserted non-empty by check-required-secrets.sh,
    which runs unconditionally there."""
    ci = load_ci()
    script = (REPO_ROOT / "scripts" / "ci" / "check-required-secrets.sh").read_text(
        encoding="utf-8"
    )
    gating = set()
    for name in ["release:build-images", "muma-mobile:build-release"]:
        for rule in ci[name]["rules"]:
            if not isinstance(rule, dict):
                continue
            for var in re.findall(r"\$([A-Z][A-Z0-9_]*)", rule.get("if", "")):
                if not var.startswith("CI_"):
                    gating.add(var)
    assert gating, "no gating variables found - the extraction above broke"
    unchecked = [var for var in sorted(gating) if var not in script]
    assert unchecked == [], (
        f"these variables silently skip a release job when missing: {unchecked}"
    )


def test_db_integration_isolates_per_ci_job():
    """A fixed container name plus `docker rm -f` at both ends of the run
    means two concurrent pipelines destroy each other's database mid-test.
    The script must key its container (and port) on CI_JOB_ID like every
    compose-based job already does."""
    script = (REPO_ROOT / "scripts" / "test" / "db-integration.sh").read_text(encoding="utf-8")
    assert "CI_JOB_ID" in script


# --- `changes:` coverage ------------------------------------------------------
# A job's `changes:` list is what decides whether it runs at all on a merge
# request. When it drifts away from what the job's script actually executes,
# the job silently stops guarding that code: the merge request that broke it
# is green, and the failure lands on the next unrelated merge request that
# happens to touch a listed path.


def _changes_globs(ci, job):
    # A job without `rules:` runs in every pipeline, so it is triggered by more
    # than any glob could describe. It still contributes nothing here: this
    # collects the paths jobs opt in to, and counting an unconditional job as
    # coverage for a path would be the same mistake as counting "**/*".
    globs = []
    for rule in ci[job].get("rules", []):
        if isinstance(rule, dict) and "changes" in rule:
            globs.extend(rule["changes"])
    return globs


def _is_covered(path: str, globs: list[str]) -> bool:
    """True if any glob would match a file somewhere under `path`."""
    return any(glob == "**/*" or glob.startswith(path) for glob in globs)


# Directories scripts/test/music-management-unit.sh hands to pytest. It runs
# with --cov=services and --cov-fail-under, so every source directory under
# services/ counts even when it holds no tests of its own.
PYTHON_UNIT_SOURCES = [
    "services/common/",
    "services/downloader/",
    "services/importer/",
    "services/ml-analyzer/",
    "services/music_manager/",
    "services/other/",
    "services/scanner/",
    "services/tagger/",
    "services/tests/",
    "tests/ci/",
    "tools/",
]


def test_python_unit_job_runs_for_every_directory_it_tests():
    ci = load_ci()
    globs = _changes_globs(ci, "music-management:unit")
    missing = [path for path in PYTHON_UNIT_SOURCES if not _is_covered(path, globs)]
    assert missing == [], (
        "music-management:unit collects these but no `changes:` glob triggers it "
        f"for them: {missing}"
    )


# scripts/lint.sh: TARGET=${1:-services/ tools/ tests/}
LINT_SOURCES = ["services/", "tools/", "tests/"]


def test_lint_job_runs_for_every_directory_it_lints():
    ci = load_ci()
    globs = _changes_globs(ci, "quality:lint")
    missing = [path for path in LINT_SOURCES if not _is_covered(path, globs)]
    assert missing == [], f"quality:lint lints these but is not triggered by them: {missing}"


# --- Docker image coverage ---------------------------------------------------
# A merge request that changed only a Dockerfile used to match no `changes:`
# rule in the whole file and ran nothing but the secret scan. The first build
# was release:build-images, on a release branch, minutes before deploy:prod.


def _matches_file(glob: str, path: str) -> bool:
    """Approximate GitLab's `changes:` matching for a single file path."""
    pattern = re.escape(glob).replace(r"\*\*/\*", ".*").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(pattern, path) is not None


def _all_changes_globs(ci: dict) -> list[str]:
    globs: list[str] = []
    for name in job_names(ci):
        # security:secret-scan matches "**/*" by design. Counting that as
        # coverage would make the test below pass for every file in the repo
        # forever, which is the opposite of what it is for.
        globs.extend(g for g in _changes_globs(ci, name) if g != "**/*")
    return globs


def test_every_dockerfile_is_built_or_tested_by_some_job():
    """Nothing may reach release:build-images having never been compiled."""
    ci = load_ci()
    globs = _all_changes_globs(ci)
    dockerfiles = [
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("Dockerfile*")
        if ".git" not in p.parts and "node_modules" not in p.parts
    ]
    assert dockerfiles, "no Dockerfiles found - the glob above is wrong"
    missing = [f for f in dockerfiles if not any(_matches_file(g, f) for g in globs)]
    assert missing == [], f"no job's `changes:` rules trigger on these Dockerfiles: {missing}"


def test_merge_request_image_build_never_pushes():
    """docker:build-images runs on merge requests, where a push would publish
    an unreviewed image to the tag production pulls."""
    ci = load_ci()
    assert ci["docker:build-images"]["variables"]["PUSH_IMAGES"] == "false"


def test_the_release_image_build_still_pushes():
    """The inverse of the test above: PUSH_IMAGES defaults to true, and
    release:build-images must never be the job that opts out."""
    ci = load_ci()
    assert "false" not in str(ci["release:build-images"].get("variables", {}))


# --- The deploy actually has to be verified ----------------------------------


def test_ci_deploy_ends_in_a_gate_that_can_fail():
    """ci-deploy.sh used to end with two `docker ps --format` calls whose
    output nobody inspected, then echo success unconditionally. `docker ps`
    exits 0 for a restart-looping container and for an empty stack alike."""
    script = (REPO_ROOT / "scripts" / "ci-deploy.sh").read_text(encoding="utf-8")
    assert "post-deploy-verify.sh" in script


def test_deploy_smoke_runs_on_every_release_branch():
    ci = load_ci()
    condition = first_condition(ci, "deploy:smoke")
    assert "release" in condition and "hotfix" in condition
    assert ci["deploy:smoke"]["needs"] == ["deploy:prod"]


def test_tagging_is_gated_on_what_production_actually_serves():
    """Release 0.19.0 was tagged on master and back-merged to develop while
    production sat on 0.18.2: deploy:prod was skipped, and a skipped job blocks
    nothing. Stage ordering cannot catch that -- only asking production can."""
    ci = load_ci()
    assert ci["release:tag"]["needs"] == ["release:verify-deployed"]
    assert first_condition(ci, "release:verify-deployed") == '$CI_COMMIT_BRANCH == "master"'


# --- DAG correctness ---------------------------------------------------------


def test_needs_on_a_conditional_job_is_optional():
    """Almost every job here has `changes:` rules, so it is frequently absent
    from the pipeline. A non-optional `needs:` on an absent job is a
    pipeline-level YAML error that drops the whole pipeline, not a skip."""
    ci = load_ci()
    conditional = {
        name
        for name in job_names(ci)
        if any("changes" in rule for rule in ci[name].get("rules", []) if isinstance(rule, dict))
    }
    offenders = []
    for name in job_names(ci):
        for need in ci[name].get("needs", []):
            target = need["job"] if isinstance(need, dict) else need
            optional = isinstance(need, dict) and need.get("optional") is True
            if target in conditional and not optional:
                offenders.append(f"{name} needs {target}")
    assert not offenders, f"these needs must be `optional: true`: {offenders}"


def test_integration_jobs_do_not_wait_for_the_android_build():
    """muma-mobile:check ran 37 minutes on the 0.19.0 pipeline and every
    integration job sat behind it for a result none of them use."""
    ci = load_ci()
    for name in ["db:integration", "contracts", "frontend:browser"]:
        needs = ci[name].get("needs")
        assert needs is not None, f"{name} still waits for the entire unit stage"
        targets = [n["job"] if isinstance(n, dict) else n for n in needs]
        assert "muma-mobile:check" not in targets


# --- Artifacts ---------------------------------------------------------------


def test_coverage_reports_are_uploaded_even_when_the_job_fails():
    """Same reason as the junit reports: the run worth inspecting is the one
    that failed, and that is exactly the run whose report was dropped."""
    ci = load_ci()
    offenders = []
    for name in job_names(ci):
        artifacts = ci[name].get("artifacts", {})
        if "coverage_report" in artifacts.get("reports", {}) and artifacts.get("when") != "always":
            offenders.append(name)
    assert not offenders, f"coverage report lost on failure for: {offenders}"


def test_no_job_ships_environment_debugging():
    """music-management:unit carried an `ENV DEBUG` block - hostname, ip addr,
    whoami, ls of the runner build dir - in every single run."""
    ci = load_ci()
    offenders = [
        name
        for name in job_names(ci)
        for line in ci[name].get("script", [])
        if isinstance(line, str) and ("ip addr" in line or "ENV DEBUG" in line)
    ]
    assert offenders == [], f"leftover debugging in: {offenders}"


def test_branch_cleanup_does_not_depend_on_the_tag_or_the_deploy():
    """Deleting a branch already merged into master is safe whatever the tag
    and the deploy did. While the delete was the tail of back-merge-develop.sh
    it inherited release:tag's needs, so a failing release:verify-deployed -
    production not serving what master says - left the merged release branch
    alive, which is the precondition for
    docs/bug-reports/016-stale-release-branch-clobbered-latest-deploy.md."""
    ci = load_ci()
    job = ci["release:cleanup-branch"]
    assert job["needs"] == [], "cleanup must not wait on the tag or the deploy"
    assert first_condition(ci, "release:cleanup-branch") == '$CI_COMMIT_BRANCH == "master"'


def test_the_back_merge_no_longer_deletes_branches():
    """Two jobs racing to delete the same branch, one of them behind an early
    `exit 0`, is how this got confusing in the first place."""
    script = (REPO_ROOT / "scripts" / "ci" / "back-merge-develop.sh").read_text(encoding="utf-8")
    assert "repository/branches/" not in script
