"""The pipeline policy, as executable assertions.

Every rule here exists because breaking it has a concrete production
consequence, named in the test's docstring. See
docs/superpowers/plans/2026-08-02-ci-release-hardening.md.
"""

from tests.ci.conftest import job_names, load_ci


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
    "lms:unit",
    "frontend:unit",
    "ultrasonic:check",
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
        ("ultrasonic:check", "services/ultrasonic/ultrasonic/build/test-results/**/TEST-*.xml"),
    ]:
        assert ci[name]["artifacts"]["reports"]["junit"] == path


def test_junit_artifacts_are_uploaded_even_when_the_job_fails():
    """A report that only appears on success is exactly backwards."""
    ci = load_ci()
    for name in ["music-management:unit", "ultrasonic:check"]:
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
    "ultrasonic:build-release",
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
