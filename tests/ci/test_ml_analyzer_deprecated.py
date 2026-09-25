"""The ml-analyzer stays deprecated until someone decides otherwise.

Decided 2026-09-25: the service is disabled, not deleted
(services/ml-analyzer/DEPRECATED.md). These assertions keep it from drifting
back into the default pipeline, the build or a compose file one convenient line
at a time -- each of which would cost CI time, or production resources, for code
that is known not to work. Reviving it is a deliberate change that deletes or
rewrites this file, following the checklist in DEPRECATED.md.
"""

import json
import tomllib

import yaml

from tests.ci.conftest import REPO_ROOT, job_names, load_ci

SERVICE_DIR = REPO_ROOT / "services" / "ml-analyzer"
MANUAL_JOB = "backend:ml-analyzer-unit"
# What marks a job as building or testing the service: its directory, its tests,
# or the script that runs them.
MARKERS = ("services/ml-analyzer", "MlAnalyzer", "ml-analyzer-unit.sh")


def test_deprecation_notice_exists():
    """The decision and the revive checklist live in DEPRECATED.md; the README points at it."""
    notice = SERVICE_DIR / "DEPRECATED.md"
    assert notice.is_file(), "services/ml-analyzer/DEPRECATED.md is missing"
    text = notice.read_text(encoding="utf-8")
    assert "To revive" in text, "DEPRECATED.md lost its revive checklist"
    readme_head = (SERVICE_DIR / "README.md").read_text(encoding="utf-8")[:1500]
    assert "DEPRECATED.md" in readme_head, "the README no longer opens with the deprecation notice"


def test_no_default_job_references_the_service():
    """Only the manual job may build or test it; any other job would run it by default."""
    ci = load_ci()
    offenders = [
        name
        for name in job_names(ci)
        if name != MANUAL_JOB and any(marker in json.dumps(ci[name]) for marker in MARKERS)
    ]
    assert offenders == [], f"these jobs reference the deprecated ml-analyzer: {offenders}"


def test_the_manual_job_stays_manual():
    """The one job that tests it must never start by itself or block a pipeline."""
    ci = load_ci()
    assert MANUAL_JOB in ci, f"{MANUAL_JOB} is gone; the kept code can no longer be tested"
    job = ci[MANUAL_JOB]
    assert job.get("allow_failure") is True
    for rule in job["rules"]:
        if not isinstance(rule, dict):
            continue  # a !reference to a shared guard template
        assert rule.get("when") in ("manual", "never"), f"{MANUAL_JOB} has a rule that runs it automatically: {rule}"


def test_the_default_suite_skips_it_and_coverage_omits_it():
    """Skipped tests with counted source would read as ~0% coverage and drag the floor."""
    script = (REPO_ROOT / "scripts" / "test" / "music-management-unit.sh").read_text(encoding="utf-8")
    assert "--ignore=services/ml-analyzer" in script
    assert "--ignore-glob=services/tests/MlAnalyzer*Test.py" in script
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "services/ml-analyzer/*" in config["tool"]["coverage"]["run"]["omit"]


def test_no_compose_file_defines_the_service():
    """Its compose service stays commented out everywhere, not only in the deploy file."""
    offenders = []
    for path in sorted((REPO_ROOT / "docker").glob("*compose*.yml")):
        services = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("services") or {}
        if "ml-analyzer" in services:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"ml-analyzer is an active compose service in: {offenders}"


def test_build_all_leaves_it_out():
    """`./build.sh` with no arguments builds every image; ml is only built when named."""
    script = (REPO_ROOT / "build.sh").read_text(encoding="utf-8")
    build_all = script.split('echo "--- Building all modules in parallel ---"', 1)[1].split("else", 1)[0]
    assert "build_ml" not in build_all


def test_renovate_ignores_it():
    """No dependency merge requests for code that is not built or deployed."""
    config = json.loads((REPO_ROOT / "renovate.json").read_text(encoding="utf-8"))
    assert any(
        rule.get("matchFileNames") == ["services/ml-analyzer/**"] and rule.get("enabled") is False
        for rule in config["packageRules"]
    )
