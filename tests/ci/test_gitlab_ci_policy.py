"""The pipeline policy, as executable assertions.

Every rule here exists because breaking it has a concrete production
consequence, named in the test's docstring.
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


# Jobs that gate a release. If one of these does not run on a release branch,
# release:build-images publishes code this pipeline never tested.
GATING_JOBS = [
    "backend:format",
    "backend:lint",
    "backend:typecheck",
    "backend:unit",
    "server:unit",
    "frontend:unit",
    "mobile:format",
    "mobile:lint",
    "mobile:unit",
    "mobile:smoke",
]


def test_gating_jobs_always_run_on_a_release_branch():
    """A `changes:`-only rule skips these on the stabilize commit, which
    touches nothing but VERSION/CHANGELOG/RELEASE_NOTES -- and a skipped job
    does not block release:build-images."""
    ci = load_ci()
    for name in GATING_JOBS:
        rules = ci[name]["rules"]
        assert any(rule == [".release_rule", "rules"] for rule in rules), (
            f"{name} does not reference .release_rule, so it can be skipped on a release branch"
        )


# A dedicated schedule sets exactly one of these, and exists to run exactly one
# job. Everything else must step aside.
SCHEDULE_OWNED_JOBS = {
    "deps:renovate": "$RENOVATE",
    "muma:refresh-downloader": "$REFRESH_DOWNLOADER",
    "runner:disk-janitor": "$DISK_JANITOR",
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
        name for name in job_names(ci) if name not in SCHEDULE_OWNED_JOBS and GUARD not in ci[name].get("rules", [])
    ]
    assert offenders == [], f"these jobs would run on every dedicated schedule: {offenders}"


def test_the_guard_is_the_first_rule():
    """Rules are evaluated in order and the first match wins. A guard placed
    after a `changes:` rule never gets the chance to say no."""
    ci = load_ci()
    misplaced = [
        name for name in job_names(ci) if name not in SCHEDULE_OWNED_JOBS and ci[name].get("rules", [None])[0] != GUARD
    ]
    assert misplaced == [], f"guard is not the first rule on: {misplaced}"


def test_the_job_a_schedule_exists_for_is_not_guarded():
    """The inverse, and the one that actually breaks the feature: guarding
    deps:renovate would mean the renovate schedule runs nothing at all."""
    ci = load_ci()
    for name, variable in SCHEDULE_OWNED_JOBS.items():
        assert GUARD not in ci[name]["rules"], f"{name} must not step aside for its own schedule"
        conditions = " ".join(rule.get("if", "") for rule in ci[name]["rules"] if isinstance(rule, dict))
        assert variable in conditions, f"{name} does not check {variable}"


def test_the_guard_covers_every_schedule_variable():
    """A new dedicated schedule whose variable is missing here silently gets the
    old behaviour: one job asked for, the whole suite delivered."""
    ci = load_ci()
    condition = ci[".dedicated_schedule_guard"]["rules"][0]["if"]
    for variable in SCHEDULE_OWNED_JOBS.values():
        assert variable in condition, f"{variable} is not in the guard"
    assert ci[".dedicated_schedule_guard"]["rules"][0]["when"] == "never"


MASTER_GUARD = [".not_on_master", "rules"]


def test_master_runs_the_release_sequence_and_nothing_else():
    """A push to master is the merge of a release/hotfix tip that already
    passed the full gated pipeline, and master receives nothing else -- but
    the `changes:` rules see the whole release as the diff and re-ran the
    backend, server and integration jobs on an identical tree (pipeline 3200:
    20 job minutes), with release:tag waiting behind them in a later stage."""
    ci = load_ci()
    unguarded = [
        name
        for name in job_names(ci)
        if not name.startswith("release:")
        and name not in SCHEDULE_OWNED_JOBS
        and MASTER_GUARD not in ci[name].get("rules", [])
    ]
    assert unguarded == [], f"these jobs would re-test master's identical tree: {unguarded}"
    guarded_release_jobs = [
        name for name in job_names(ci) if name.startswith("release:") and MASTER_GUARD in ci[name].get("rules", [])
    ]
    assert guarded_release_jobs == [], f"the release sequence must run on master: {guarded_release_jobs}"


def test_the_master_guard_only_covers_push_pipelines():
    """muma:refresh-downloader is a schedule that lives on master. A guard on
    $CI_COMMIT_BRANCH alone would step aside for it too."""
    ci = load_ci()
    rule = ci[".not_on_master"]["rules"][0]
    assert rule["when"] == "never"
    assert '$CI_COMMIT_BRANCH == "master"' in rule["if"]
    assert '$CI_PIPELINE_SOURCE == "push"' in rule["if"]


def test_the_master_guard_precedes_every_positive_rule():
    """Rules are evaluated in order and the first match wins."""
    ci = load_ci()
    late = []
    for name in job_names(ci):
        rules = ci[name].get("rules", [])
        if MASTER_GUARD not in rules:
            continue
        for rule in rules[: rules.index(MASTER_GUARD)]:
            if rule == GUARD or (isinstance(rule, dict) and rule.get("when") == "never"):
                continue
            late.append(name)
            break
    assert late == [], f"a positive rule is evaluated before the master guard on: {late}"


# Every job is `<scope>:<what>`. The scope is a source component -- what you
# edited -- or `muma` when the job spans them, or a concern that belongs to no
# component. Adding one here is a deliberate act: three competing schemes at
# once is how this drifted the first time.
COMPONENT_SCOPES = {
    "backend",  # the Python tree: 5 shipped images, 384 files
    "server",  # the C++ playback server
    "frontend",  # the Svelte web UI (ships inside the server image)
    "mobile",  # the Android app
}

JOB_SCOPES = COMPONENT_SCOPES | {
    "muma",  # spans components, or is the whole product
    "security",
    "deps",
    "runner",
    "release",
    "public",  # what the public mirror may contain (personal data check)
}

# What each component is checked for. Every component has all three; anything
# beyond them is component-specific and lives in EXTRA_VERBS.
CORE_VERBS = {"format", "lint", "unit"}
EXTRA_VERBS = {
    # typecheck-all is the whole tree at the loose floor; typecheck is the strict list.
    # ml-analyzer-unit is the deprecated ml-analyzer's manual test job, kept out of
    # backend:unit (services/ml-analyzer/DEPRECATED.md).
    "backend": {"typecheck", "typecheck-all", "integration", "ml-analyzer-unit"},
    # `bundle` produces services/frontend/dist as an artifact for the Android build, which
    # runs in an image without Node. It is a frontend job because it is the frontend's own
    # toolchain that builds it; it is not a check, which is why it needs a verb of its own.
    "frontend": {"typecheck", "e2e", "bundle"},
    "mobile": {"smoke", "build-debug", "build-release"},
    "server": set(),
}


def test_every_job_is_scoped():
    """A red job should say whose problem it is before you open it. `contracts`
    said nothing; `quality:cpp-format` said "quality" about a job that only ever
    touches the C++ server, whose own tests answered to a different prefix."""
    ci = load_ci()
    unscoped = [name for name in job_names(ci) if ":" not in name]
    assert unscoped == [], f"jobs without a scope: {unscoped}"

    unknown = sorted({name.split(":", 1)[0] for name in job_names(ci)} - JOB_SCOPES)
    assert unknown == [], (
        f"unknown job scopes: {unknown}. Add it to JOB_SCOPES only if it is a "
        "real component or concern, not to make a one-off name pass."
    )


def test_every_component_is_checked_the_same_way():
    """The point of the scheme: the same three questions are asked of every
    component, so a gap is visible as a missing job rather than as something
    nobody thought to add. Each of these was genuinely absent at some point --
    the frontend had no format check, the server had no linter at all."""
    ci = load_ci()
    names = set(job_names(ci))
    missing = {
        f"{component}:{verb}"
        for component in COMPONENT_SCOPES
        for verb in CORE_VERBS
        if f"{component}:{verb}" not in names
    }
    assert missing == set(), f"components missing a core check: {sorted(missing)}"


def test_component_jobs_use_a_known_verb():
    """Keeps the second half of the name as disciplined as the first: a new
    `mobile:checkstuff` has to be either a core verb or an admitted extra."""
    ci = load_ci()
    offenders = []
    for name in job_names(ci):
        scope, _, verb = name.partition(":")
        if scope not in COMPONENT_SCOPES:
            continue
        if verb not in CORE_VERBS | EXTRA_VERBS[scope]:
            offenders.append(name)
    assert offenders == [], f"component jobs with an unknown verb: {offenders}"


def test_the_disk_janitor_stays_untagged():
    """Runner selection here is the absence of a tag. Both runners carry
    `fast`, so tagging this would hand it to whichever polls first -- a coin
    flip between the host that fills up and a desktop that is usually off.
    Untagged always lands on the always-on LXC."""
    ci = load_ci()
    assert "tags" not in ci["runner:disk-janitor"]


def test_credentialed_jobs_never_carry_the_fast_tag():
    """Both runners answer to `fast`, and one of them is a desktop. A job that
    holds the production SSH key, pushes a tag or signs and uploads the APK
    must be pinned to the always-on LXC, which is what being untagged means."""
    ci = load_ci()
    credentialed = [
        "mobile:build-release",
        "release:publish",
        "release:tag",
        "release:build-images",
        "release:cleanup-branch",
        "release:back-merge-develop",
    ]
    offenders = [name for name in credentialed if "tags" in ci.get(name, {})]
    assert offenders == [], f"credentialed jobs must stay LXC-only: {offenders}"


def test_host_pytest_jobs_are_not_handed_to_the_second_runner():
    """muma:contracts starts its stack in Docker but runs the tests from the
    host, and only the LXC has pytest installed. Tagging it (and, back then,
    backend:integration) on the strength of the `docker` line in its script
    failed in five seconds with `No module named pytest` (pipeline 2618).
    muma:e2e may carry the tag because core-e2e.sh falls back to its own image
    when pytest-bdd is missing."""
    ci = load_ci()
    assert "tags" not in ci["muma:contracts"], "muma:contracts runs pytest on the host, keep it LXC-only"


def test_containerised_backend_suites_run_on_either_runner():
    """backend:unit and backend:integration run pytest inside
    docker/Dockerfile.python-ci (bug report 050), built on whichever host runs
    the job, so the runner's own Python no longer decides the result and the
    workstation may take them (GitLab issue #27). The tag is only safe while
    that stays true -- test_backend_suites_run_in_the_container_in_ci pins it."""
    ci = load_ci()
    for name in ("backend:unit", "backend:integration"):
        assert ci[name].get("tags") == [".fast_runner", "tags"], f"{name} should reference .fast_runner tags"


def test_integration_database_is_per_job_on_a_shared_host():
    """backend:integration may run twice on one host (two pipelines, either
    runner). A fixed container name let one job `docker rm -f` the other's
    database mid-run; a pre-picked port can be taken between picking and
    `docker run`. The name carries CI_JOB_ID and Docker assigns the port, on
    loopback only."""
    text = (REPO_ROOT / "scripts" / "test" / "db-integration.sh").read_text(encoding="utf-8")
    assert "muma-integration-db${CI_JOB_ID:+-$CI_JOB_ID}" in text
    assert 'PUBLISH="127.0.0.1::3306"' in text
    assert 'docker port "$CONTAINER" 3306/tcp' in text
    assert '-p "$HOST_PORT:3306"' not in text, "a bare host port publishes on every interface"


def test_release_rule_covers_release_and_hotfix():
    ci = load_ci()
    condition = ci[".release_rule"]["rules"][0]["if"]
    assert "release" in condition and "hotfix" in condition


def test_no_job_deploys():
    """This repository builds and publishes; an installation deploys from the
    release tag (docs/designs/ops-split/). A job here that runs the deploy
    would deploy beside the installation's own, and the two would race."""
    ci = load_ci()
    offenders = [
        name
        for name in job_names(ci)
        if "environment" in ci[name]
        or any("ci-deploy.sh" in line for line in ci[name].get("script", []) if isinstance(line, str))
    ]
    assert offenders == [], f"these jobs deploy: {offenders}"


def test_feature_branches_get_no_branch_pipeline():
    """A feature branch's first push has no CI_COMMIT_BEFORE_SHA, so every
    `changes:` rule is true and the branch pipeline runs the entire file --
    seconds before the MR pipeline runs the jobs the diff actually touched
    (pipeline 3203 vs 3204: 66 job minutes against 21). The old dedupe keyed on
    $CI_OPEN_MERGE_REQUESTS, which is unset at exactly that moment. Branch
    pipelines exist for release/hotfix, develop and master only; a feature
    branch is tested through its merge request."""
    ci = load_ci()
    admitted = [
        rule["if"]
        for rule in ci["workflow"]["rules"]
        if rule.get("when") != "never" and "$CI_COMMIT_BRANCH" in rule.get("if", "")
    ]
    assert admitted, "no workflow rule admits any branch pipeline"
    for condition in admitted:
        assert re.search(r'\$CI_COMMIT_BRANCH\s*(=~|==)', condition), (
            f"a bare $CI_COMMIT_BRANCH admits every feature branch's first push: {condition}"
        )
        assert "$CI_OPEN_MERGE_REQUESTS" not in condition
    branches = " ".join(admitted)
    assert "release" in branches and "hotfix" in branches
    assert '"develop"' in branches and '"master"' in branches


def test_hand_started_pipelines_still_run_on_any_branch():
    """MUMA_UPDATE_SNAPSHOTS=1 is a Run-pipeline on whatever branch needs new
    references. Restricting branch pipelines to develop/master must not take
    that away."""
    ci = load_ci()
    sources = " ".join(rule.get("if", "") for rule in ci["workflow"]["rules"] if rule.get("when") != "never")
    assert '$CI_PIPELINE_SOURCE == "web"' in sources
    assert '$CI_PIPELINE_SOURCE == "merge_request_event"' in sources


def test_release_branches_do_not_get_a_merge_request_pipeline():
    """The push-vs-MR dedupe keys on $CI_OPEN_MERGE_REQUESTS, which only exists
    in push pipelines -- so a release branch with an open MR got a branch
    pipeline AND an MR pipeline, ran everything twice, and the two Android jobs
    raced each other for the shared Gradle home. The branch pipeline is where
    the release images and the APK are built, so the MR pipeline is the one
    that must never start."""
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
    """release:build-images matches on $CI_COMMIT_BRANCH, which is unset in a
    merge request pipeline. If the duplicate-pipeline guard fired for a release
    branch that happens to have an MR open, the branch pipeline would vanish
    and the release would never be built at all. The release rule therefore
    has to be decided before the guard is reached."""
    ci = load_ci()
    rules = ci["workflow"]["rules"]
    for rule in rules:
        condition = rule.get("if", "")
        if "release" in condition and "hotfix" in condition:
            assert rule.get("when") != "never"
            break
        assert rule.get("when") != "never", (
            "a `when: never` rule is evaluated before release/hotfix branches are allowed through"
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


def _minutes(value: str) -> int:
    match = re.fullmatch(r"(\d+)m", value)
    assert match, f"expected a plain minute value, got {value!r}"
    return int(match.group(1))


def test_mobile_jobs_remove_their_container_on_timeout():
    """The muma-mobile resource group only serialises the *jobs*. When job
    30995 timed out, the runner killed its shell and the foreground
    `docker run` lived on for an hour with a Gradle daemon holding
    journal-1.lock, so every mobile job that landed on that runner meanwhile
    died in 60 seconds through no fault of its own. after_script removes the
    container by its ci.job label -- and on a timeout after_script only runs
    if the runner stopped the script itself, which needs RUNNER_SCRIPT_TIMEOUT
    below the job timeout."""
    ci = load_ci()
    mobile_jobs = [name for name in job_names(ci) if name.startswith("mobile:")]
    assert mobile_jobs
    cleanup = ci[".mobile_container"]["after_script"]
    assert any("label=ci.job=$CI_JOB_ID" in line and "docker rm -f" in line for line in cleanup)
    for name in mobile_jobs:
        job = ci[name]
        assert job.get("after_script") == [".mobile_container", "after_script"], f"{name} leaves its container behind"
        variables = job.get("variables", {})
        assert "RUNNER_AFTER_SCRIPT_TIMEOUT" in variables, f"{name} has no after_script budget"
        script_budget = variables.get("RUNNER_SCRIPT_TIMEOUT")
        assert script_budget, f"{name}: without RUNNER_SCRIPT_TIMEOUT after_script does not run on timeout"
        assert _minutes(script_budget) < _minutes(job["timeout"]), (
            f"{name}: RUNNER_SCRIPT_TIMEOUT must be below the job timeout or the job dies first"
        )


def test_every_mobile_container_carries_the_job_label():
    """The after_script above finds containers by label. A mobile script that
    starts one without it is back to the orphan."""
    scripts = [
        "scripts/test/muma-mobile-unit.sh",
        "scripts/test/muma-mobile-ktlint.sh",
        "scripts/test/muma-mobile-detekt.sh",
        "scripts/test/muma-mobile-lint.sh",
        "scripts/test/muma-mobile-emulator-smoke.sh",
        "scripts/ci/muma-mobile-build-upload.sh",
    ]
    for script in scripts:
        text = (REPO_ROOT / script).read_text(encoding="utf-8")
        runs = text.count("\ndocker run ")
        labelled = text.count('--label "ci.job=${CI_JOB_ID:-local}"')
        assert runs and runs == labelled, f"{script}: {runs} docker run, {labelled} with the ci.job label"


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
        ("backend:unit", "report-python.xml"),
        # Every module, not just app/: a glob pinned to one module means a new module's
        # tests report green by publishing nothing at all.
        ("mobile:unit", "services/muma-mobile/**/build/test-results/**/TEST-*.xml"),
        # Kept in lockstep with playwright.config.js's junit reporter outputFile.
        ("frontend:e2e", "services/frontend/test-results/junit-browser.xml"),
    ]:
        assert ci[name]["artifacts"]["reports"]["junit"] == path


def test_junit_artifacts_are_uploaded_even_when_the_job_fails():
    """A report that only appears on success is exactly backwards."""
    ci = load_ci()
    for name in ["backend:unit", "mobile:unit", "frontend:e2e"]:
        assert ci[name]["artifacts"]["when"] == "always"


def test_screenshot_diffs_soften_the_browser_job_only_through_exit_42():
    """frontend-browser.sh exits 42 when nothing but the screenshot suite
    differs from its references (docs/frontend-screenshots.md). That, and only
    that, may turn the job orange: a blanket `allow_failure: true` would also
    wave through a failing login or a route that never rendered. The
    references themselves ride along as an artifact, because a refreshed set
    (MUMA_UPDATE_SNAPSHOTS=1) has no other way back into the tree."""
    ci = load_ci()
    job = ci["frontend:e2e"]
    assert job["allow_failure"] == {"exit_codes": [42]}
    assert "services/frontend/tests/browser/__screenshots__/" in job["artifacts"]["paths"]


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
    "mobile:build-release",
]


def test_hotfix_branches_get_the_full_release_treatment():
    """A hotfix that skips the secret check or the version check is a hotfix
    that deploys unverified straight to production."""
    ci = load_ci()
    for name in RELEASE_STAGE_JOBS:
        conditions = " ".join(rule.get("if", "") for rule in ci[name]["rules"] if isinstance(rule, dict))
        assert "hotfix" in conditions, f"{name} does not run on a hotfix branch"


def test_release_apk_waits_for_the_android_unit_tests():
    """`needs:` bypasses stage ordering, and the muma-mobile resource group
    only serializes jobs, it does not order them. With version-check as the
    only need, mobile:build-release built and UPLOADED a signed APK while
    mobile:unit on the same commit failed -- phones auto-update from the
    hoster, so users got untested code even though the server release
    correctly never shipped."""
    ci = load_ci()
    targets = [n["job"] if isinstance(n, dict) else n for n in ci["mobile:build-release"]["needs"]]
    assert "mobile:unit" in targets
    assert "release:version-check" in targets
    # And the emulator smoke test: a release APK that crashes on startup must
    # never reach the hoster (docs/bug-reports/029 shipped exactly that way).
    assert "mobile:smoke" in targets


def test_publishing_jobs_are_not_interruptible():
    """`default: interruptible: true` lets a newer push cancel a running job.
    Fine for tests; not for anything that publishes or mutates the outside
    world halfway through."""
    ci = load_ci()
    for name in [
        "release:build-images",
        "mobile:build-release",
        "release:publish",
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
    script = (REPO_ROOT / "scripts" / "ci" / "check-required-secrets.sh").read_text(encoding="utf-8")
    gating = set()
    for name in ["release:build-images", "mobile:build-release"]:
        for rule in ci[name]["rules"]:
            if not isinstance(rule, dict):
                continue
            for var in re.findall(r"\$([A-Z][A-Z0-9_]*)", rule.get("if", "")):
                if not var.startswith("CI_"):
                    gating.add(var)
    assert gating, "no gating variables found - the extraction above broke"
    unchecked = [var for var in sorted(gating) if var not in script]
    assert unchecked == [], f"these variables silently skip a release job when missing: {unchecked}"


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
# services/ counts even when it holds no tests of its own. The deprecated
# services/ml-analyzer is the exception: skipped by the script and omitted from
# coverage, see tests/ci/test_ml_analyzer_deprecated.py.
PYTHON_UNIT_SOURCES = [
    "services/common/",
    "services/downloader/",
    "services/importer/",
    "services/music_manager/",
    "services/scanner/",
    "services/tagger/",
    "services/tests/",
    "tests/ci/",
    "tests/unit/",
    "tools/",
]


def test_python_unit_job_runs_for_every_directory_it_tests():
    ci = load_ci()
    globs = _changes_globs(ci, "backend:unit")
    missing = [path for path in PYTHON_UNIT_SOURCES if not _is_covered(path, globs)]
    assert missing == [], f"backend:unit collects these but no `changes:` glob triggers it for them: {missing}"


# scripts/lint.sh: TARGET=${1:-services/ tools/ tests/}
LINT_SOURCES = ["services/", "tools/", "tests/"]


def test_the_smoke_apk_always_carries_the_web_bundle():
    """mobile:smoke proves the Capacitor plugins survived R8 by reading a value
    off the Svelte login page. Without frontend:bundle in the same pipeline the
    APK carries the placeholder page instead, and that check silently degrades
    to "the WebView came up" -- so every path that starts the smoke must also
    start the bundle (issue #24)."""
    ci = load_ci()
    bundle = _changes_globs(ci, "frontend:bundle")
    missing = [glob for glob in _changes_globs(ci, "mobile:smoke") if glob not in bundle]
    assert missing == [], f"mobile:smoke runs for these without frontend:bundle: {missing}"
    needs = [n["job"] if isinstance(n, dict) else n for n in ci["mobile:smoke"]["needs"]]
    assert "frontend:bundle" in needs


def test_lint_job_runs_for_every_directory_it_lints():
    ci = load_ci()
    globs = _changes_globs(ci, "backend:lint")
    missing = [path for path in LINT_SOURCES if not _is_covered(path, globs)]
    assert missing == [], f"backend:lint lints these but is not triggered by them: {missing}"


# --- Docker image coverage ---------------------------------------------------
# A merge request that changed only a Dockerfile used to match no `changes:`
# rule in the whole file and ran nothing but the secret scan. The first build
# was release:build-images, on a release branch, minutes before the release tag.


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
    """muma:images runs on merge requests, where a push would publish
    an unreviewed image to the tag production pulls."""
    ci = load_ci()
    assert ci["muma:images"]["variables"]["PUSH_IMAGES"] == "false"


def test_the_release_image_build_still_pushes():
    """The inverse of the test above: PUSH_IMAGES defaults to true, and
    release:build-images must never be the job that opts out."""
    ci = load_ci()
    assert "false" not in str(ci["release:build-images"].get("variables", {}))


def test_two_release_image_builds_never_run_at_once():
    """Both push the same :rc tags; interleaved, production could pull a mix of two releases (#226)."""
    ci = load_ci()
    assert ci["release:build-images"]["resource_group"] == "release-images"


def _change_globs(ci, job):
    """Every `changes:` path a job's rules list."""
    return [path for rule in ci[job]["rules"] if isinstance(rule, dict) for path in rule.get("changes", [])]


def test_a_requirements_change_runs_the_jobs_it_feeds():
    """requirements-dev.txt holds ruff, pylint and mypy; requirements.txt goes into the images (#226)."""
    ci = load_ci()
    for job in ("backend:format", "backend:lint", "backend:typecheck", "backend:typecheck-all"):
        assert "requirements-dev.txt" in _change_globs(ci, job), job
    assert "requirements.txt" in _change_globs(ci, "muma:images")


# --- The deploy actually has to be verified ----------------------------------


def test_ci_deploy_ends_in_a_gate_that_can_fail():
    """ci-deploy.sh used to end with two `docker ps --format` calls whose
    output nobody inspected, then echo success unconditionally. `docker ps`
    exits 0 for a restart-looping container and for an empty stack alike."""
    script = (REPO_ROOT / "scripts" / "ci-deploy.sh").read_text(encoding="utf-8")
    assert "post-deploy-verify.sh" in script


def test_tagging_is_gated_on_what_the_release_published():
    """The tag is what an installation deploys. Release 0.19.0 was tagged while
    its mobile job had failed and release:build-images was skipped, and a
    skipped job blocks nothing. Stage ordering cannot catch that -- only asking
    the release branch pipeline and the package registry can."""
    ci = load_ci()
    assert ci["release:tag"]["needs"] == ["release:publish"]
    assert ci["release:publish"]["needs"] == []
    assert first_condition(ci, "release:publish") == '$CI_COMMIT_BRANCH == "master"'
    assert ci["release:publish"]["script"] == ["./scripts/ci/check-release-published.sh"]


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
    """The Android jobs ran 37 minutes on the 0.19.0 pipeline and every
    integration job sat behind it for a result none of them use."""
    ci = load_ci()
    for name in ["backend:integration", "muma:contracts", "frontend:e2e"]:
        needs = ci[name].get("needs")
        assert needs is not None, f"{name} still waits for the entire unit stage"
        targets = [n["job"] if isinstance(n, dict) else n for n in needs]
        assert not any(t.startswith("mobile:") for t in targets)


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
    """backend:unit carried an `ENV DEBUG` block - hostname, ip addr,
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
    it inherited release:tag's needs, so a failing gate in front of the tag
    left the merged release branch
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


# --- Deploy order and the CI Python (bug report 050) -------------------------


def test_latest_is_only_moved_by_the_deploy():
    """release:build-images used to push :latest before the deploy had
    migrated anything, so Watchtower could start a release's code early -- or
    without any deploy, when the deploy was skipped. :latest now moves inside
    the deploy, after the backup and the migrations."""
    build = (REPO_ROOT / "scripts" / "ci" / "build-and-push-images.sh").read_text(encoding="utf-8")
    pushes = [line.strip() for line in build.splitlines() if line.strip().startswith("docker_push")]
    assert pushes, "the release build must still push"
    offenders = [line for line in pushes if ':latest"' in line or ':stable"' in line]
    assert offenders == [], f"release:build-images must not push production's tags: {offenders}"

    ci_deploy = (REPO_ROOT / "scripts" / "ci-deploy.sh").read_text(encoding="utf-8")
    assert "promote-release-images.sh" in ci_deploy


def test_backend_test_jobs_rerun_when_their_environment_changes():
    """Both suites run in docker/Dockerfile.python-ci with requirements.txt
    installed; a change to either changes what the tests run on."""
    ci = load_ci()
    for name in ("backend:unit", "backend:integration"):
        globs = _changes_globs(ci, name)
        for path in ("requirements.txt", "docker/Dockerfile.python-ci"):
            assert _is_covered(path, globs), f"{name} is not triggered by {path}"


def _python_base(dockerfile: str) -> str:
    """The python:* image a Dockerfile's last stage is built FROM."""
    froms = re.findall(r"^FROM\s+(python:\S+)", (REPO_ROOT / dockerfile).read_text(encoding="utf-8"), re.M)
    assert froms, f"{dockerfile} is not built FROM python:*"
    return froms[-1].split("-slim")[0]


def test_ci_python_is_the_python_the_images_run():
    """backend:unit ran on the runner's system python3 -- 3.11 on the LXC --
    while every image runs 3.14. The CI image and the images must agree."""
    ci_python = _python_base("docker/Dockerfile.python-ci")
    for image in ("docker/Dockerfile.music-manager", "docker/Dockerfile.base", "docker/Dockerfile.tools"):
        assert _python_base(image) == ci_python, f"{image} and docker/Dockerfile.python-ci disagree"
    tooling = (REPO_ROOT / "scripts" / "lib" / "python-tooling.sh").read_text(encoding="utf-8")
    assert f"${{PYTHON_TOOLING_IMAGE:-{ci_python}-slim}}" in tooling


def test_backend_suites_run_in_the_container_in_ci():
    for script in ("scripts/test/music-management-unit.sh", "scripts/test/db-integration.sh"):
        text = (REPO_ROOT / script).read_text(encoding="utf-8")
        assert "tooling_container_required" in text, script
        assert "tooling_use_ci_image" in text, script
        assert 'TOOLING_REQUIREMENTS="requirements.txt"' in text, script
    for script in ("scripts/lint.sh", "scripts/typecheck.sh", "scripts/format.sh"):
        assert "tooling_container_required" in (REPO_ROOT / script).read_text(encoding="utf-8"), script


# --- Honest gates (docs/bug-reports/047) --------------------------------------


def test_the_loose_type_floor_is_checked_somewhere():
    """backend:typecheck runs the strict list only, so the floor the whole tree is
    held to ran nowhere -- and could not have started, since tools/ was "found twice
    under different module names". Its backlog reached zero (GitLab issues #41 and
    #171), so it is a hard gate now: it may neither disappear nor turn orange."""
    ci = load_ci()
    job = ci["backend:typecheck-all"]
    assert job["script"] == ["./scripts/typecheck.sh --all"]
    assert not job.get("allow_failure", False)
    assert job["stage"] == "quality"
    globs = _changes_globs(ci, "backend:typecheck-all")
    assert "tools/**/*.py" in globs and "services/**/*.py" in globs
    script = (REPO_ROOT / "scripts" / "typecheck.sh").read_text(encoding="utf-8")
    assert "--explicit-package-bases services/ tools/" in script


def test_integration_job_runs_for_every_file_that_shapes_the_schema():
    """tests/integration/ builds every database from schema_tables.py, its seed rows and
    the reconcile; a change to one of them has to run that suite."""
    from tests.integration import schema_sources

    ci = load_ci()
    globs = _changes_globs(ci, "backend:integration")
    shaping = [
        schema_sources.SCHEMA_FILE,
        "services/common/schema_reconcile.py",
        "services/common/db_seeds.py",
        "services/common/db_init.py",
        *sorted(str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "services/common/seeds").glob("*.sql")),
    ]
    missing = [path for path in shaping if not any(_matches_file(glob, path) for glob in globs)]
    assert missing == [], f"these shape the schema but do not trigger backend:integration: {missing}"


def test_db_integration_runs_the_mariadb_production_runs():
    """db-integration.sh ran mariadb:10.6 for months after compose.test.yml (and
    production) moved on, so every query was proven against a server nothing ran."""
    script = (REPO_ROOT / "scripts" / "test" / "db-integration.sh").read_text(encoding="utf-8")
    compose = (REPO_ROOT / "docker" / "compose.test.yml").read_text(encoding="utf-8")
    default = re.search(r'MARIADB_VERSION="\$\{MARIADB_VERSION:-([^}]+)\}"', script)
    assert default, "db-integration.sh no longer takes MARIADB_VERSION"
    assert f"image: mariadb:{default.group(1)}" in compose


def test_unit_coverage_is_measured_on_source_only():
    """With --cov=services and no omit list the ~220 test files under services/ counted
    as covered source, and tools/ -- whose tests run -- was not measured at all."""
    import tomllib

    script = (REPO_ROOT / "scripts" / "test" / "music-management-unit.sh").read_text(encoding="utf-8")
    assert "--cov=services" in script and "--cov=tools" in script
    coverage = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["coverage"]["run"]
    assert {"*Test.py", "*/tests/*", "*/test_*.py", "*/conftest.py"} <= set(coverage["omit"])


def test_shellcheck_gates_at_warning():
    """The gate sat at `error` while 32 warnings stood open (issue #33). Those were
    fixed; dropping the floor back would let the same SC2164/SC2155 class creep
    into the deploy scripts again, unseen."""
    ci = load_ci()
    assert "./scripts/shellcheck.sh" in ci["muma:shellcheck"]["script"]
    script = (REPO_ROOT / "scripts" / "shellcheck.sh").read_text(encoding="utf-8")
    assert 'SEVERITY="${SHELLCHECK_SEVERITY:-warning}"' in script
