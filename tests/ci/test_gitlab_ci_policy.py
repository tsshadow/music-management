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
