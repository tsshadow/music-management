"""The pipeline policy, as executable assertions.

Every rule here exists because breaking it has a concrete production
consequence, named in the test's docstring. See
docs/superpowers/plans/2026-08-02-ci-release-hardening.md.
"""

import re

from tests.ci.conftest import REPO_ROOT, job_names, load_ci


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


def test_python_and_android_units_publish_junit():
    """Without this, a failed test is only visible by reading the raw log."""
    ci = load_ci()
    for name, path in [
        ("music-management:unit", "report-python.xml"),
        # Every module, not just app/: a glob pinned to one module means a new module's
        # tests report green by publishing nothing at all.
        ("muma-mobile:check", "services/muma-mobile/**/build/test-results/**/TEST-*.xml"),
    ]:
        assert ci[name]["artifacts"]["reports"]["junit"] == path


def test_junit_artifacts_are_uploaded_even_when_the_job_fails():
    """A report that only appears on success is exactly backwards."""
    ci = load_ci()
    for name in ["music-management:unit", "muma-mobile:check"]:
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


# --- `changes:` coverage ------------------------------------------------------
# A job's `changes:` list is what decides whether it runs at all on a merge
# request. When it drifts away from what the job's script actually executes,
# the job silently stops guarding that code: the merge request that broke it
# is green, and the failure lands on the next unrelated merge request that
# happens to touch a listed path.


def _changes_globs(ci, job):
    globs = []
    for rule in ci[job]["rules"]:
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
    condition = ci["deploy:smoke"]["rules"][0]["if"]
    assert "release" in condition and "hotfix" in condition
    assert ci["deploy:smoke"]["needs"] == ["deploy:prod"]


def test_tagging_is_gated_on_what_production_actually_serves():
    """Release 0.19.0 was tagged on master and back-merged to develop while
    production sat on 0.18.2: deploy:prod was skipped, and a skipped job blocks
    nothing. Stage ordering cannot catch that -- only asking production can."""
    ci = load_ci()
    assert ci["release:tag"]["needs"] == ["release:verify-deployed"]
    assert ci["release:verify-deployed"]["rules"][0]["if"] == '$CI_COMMIT_BRANCH == "master"'


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
    assert job["rules"][0]["if"] == '$CI_COMMIT_BRANCH == "master"'


def test_the_back_merge_no_longer_deletes_branches():
    """Two jobs racing to delete the same branch, one of them behind an early
    `exit 0`, is how this got confusing in the first place."""
    script = (REPO_ROOT / "scripts" / "ci" / "back-merge-develop.sh").read_text(encoding="utf-8")
    assert "repository/branches/" not in script
