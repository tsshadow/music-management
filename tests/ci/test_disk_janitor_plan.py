"""What the runner janitor is allowed to delete.

Every assertion here is a thing that, done wrong on a live runner, either
breaks a pipeline or throws away something expensive to rebuild. The selection
logic is a pure function precisely so these can be checked without a Docker
daemon and without waiting for a disk to fill.
"""

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "disk_janitor_plan.py"

_spec = importlib.util.spec_from_file_location("disk_janitor_plan", MODULE_PATH)
assert _spec and _spec.loader
plan = importlib.util.module_from_spec(_spec)
# Registered before exec: @dataclass resolves annotations through
# sys.modules[cls.__module__], which is None for a module loaded by path only.
sys.modules["disk_janitor_plan"] = plan
_spec.loader.exec_module(plan)

NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def listing(*entries: tuple[str, datetime]) -> list[str]:
    """Build `docker images` output for the given (ref, created) pairs."""
    return [
        f"{ref}\t{created.strftime('%Y-%m-%d %H:%M:%S %z')} UTC\tsha{index:012d}"
        for index, (ref, created) in enumerate(entries)
    ]


def days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


def removals(lines: list[str], **kwargs) -> list[str]:
    defaults = {"now": NOW, "keep_versions": 3, "keep_android": 2, "test_stack_min_age_hours": 2, "docker_user": "muma"}
    defaults.update(kwargs)
    return [image.ref for image in plan.select_removals(plan.parse_listing(lines), **defaults)]


def test_release_images_keep_the_newest_three_versions():
    """Every release build tags a version forever; they are all on Docker Hub."""
    lines = listing(
        ("muma/music-manager:0.38.1", days_ago(1)),
        ("muma/music-manager:0.38.0", days_ago(4)),
        ("muma/music-manager:0.37.0", days_ago(9)),
        ("muma/music-manager:0.36.0", days_ago(20)),
        ("muma/music-manager:0.13.0", days_ago(200)),
    )
    assert removals(lines) == [
        "muma/music-manager:0.13.0",
        "muma/music-manager:0.36.0",
    ]


def test_moving_tags_are_never_candidates():
    """:latest is what production pulls and :stable what LMS pulls; deleting
    either turns the next deploy into a download at best."""
    lines = listing(
        ("muma/music-manager:latest", days_ago(400)),
        ("muma/lms:stable", days_ago(400)),
        ("muma/music-manager:0.1.0", days_ago(399)),
        ("muma/music-manager:0.2.0", days_ago(398)),
        ("muma/music-manager:0.3.0", days_ago(397)),
        ("muma/music-manager:0.4.0", days_ago(396)),
    )
    assert removals(lines) == ["muma/music-manager:0.1.0"]


def test_the_keep_count_is_per_repository_not_global():
    """Otherwise a busy repository evicts a quiet one's only copies."""
    lines = listing(
        ("muma/music-manager:0.38.1", days_ago(1)),
        ("muma/music-manager:0.38.0", days_ago(2)),
        ("muma/music-manager:0.37.0", days_ago(3)),
        ("muma-ci/lms:0.38.1", days_ago(4)),
        ("muma-ci/lms:0.38.0", days_ago(5)),
    )
    assert removals(lines) == []


def test_versions_are_ranked_by_build_time_not_tag_text():
    """0.9.0 sorts after 0.13.0 as text, which would delete the newest build."""
    lines = listing(
        ("muma-ci/tools:0.13.0", days_ago(1)),
        ("muma-ci/tools:0.9.0", days_ago(30)),
        ("muma-ci/tools:0.8.0", days_ago(40)),
        ("muma-ci/tools:0.7.0", days_ago(50)),
    )
    assert removals(lines) == ["muma-ci/tools:0.7.0"]


def test_android_ci_images_keep_only_the_two_newest():
    """Tagged by Dockerfile hash and over 5GB each, so they accumulate fast."""
    lines = listing(
        ("music-management/android-ci:36-a412fdfa769e", days_ago(1)),
        ("music-management/android-ci:36-41d3e8579bda", days_ago(3)),
        ("music-management/android-ci:35-cfdcd7099e08", days_ago(30)),
        ("music-management/android-ci:35-e6d28ee7f146", days_ago(60)),
    )
    assert removals(lines) == [
        "music-management/android-ci:35-e6d28ee7f146",
        "music-management/android-ci:35-cfdcd7099e08",
    ]


def test_a_running_pipelines_test_stack_is_left_alone():
    """`docker rmi` would refuse it anyway (its containers exist), but a
    janitor that asks is a janitor whose log is readable."""
    lines = listing(
        ("muma-test-15103-music-manager:latest", NOW - timedelta(minutes=5)),
        ("muma-test-15086-music-manager:latest", days_ago(1)),
    )
    assert removals(lines) == ["muma-test-15086-music-manager:latest"]


def test_a_stranded_merge_request_build_namespace_goes_entirely():
    """build-and-push-images.sh builds under `muma-ci-<job-id>/` and removes
    that namespace on exit, so what is still here belongs to a job that never
    ran its trap. No later job reuses the namespace, which is why the count
    rule cannot apply: it would keep every dead job's `:latest` forever."""
    lines = listing(
        ("muma-ci-15540/muma-base:latest", days_ago(1)),
        ("muma-ci-15540/muma-base:0.39.0", days_ago(1)),
        ("muma-ci-15540/lms:stable", days_ago(1)),
    )
    assert removals(lines) == [
        "muma-ci-15540/muma-base:latest",
        "muma-ci-15540/muma-base:0.39.0",
        "muma-ci-15540/lms:stable",
    ]


def test_a_running_merge_request_build_is_left_alone():
    """Same reason as the test stack above: the job is still using them."""
    lines = listing(("muma-ci-15601/muma-tools:latest", NOW - timedelta(minutes=5)))
    assert removals(lines) == []


def test_third_party_images_are_never_touched():
    """Deleting mariadb or the trivy image frees little and costs a re-pull on
    the next job; an unrecognised image is not this script's business."""
    lines = listing(
        ("mariadb:10.6", days_ago(300)),
        ("phpmyadmin:latest", days_ago(300)),
        ("aquasec/trivy:latest", days_ago(300)),
        ("mobiledevops/android-sdk-image:latest", days_ago(300)),
    )
    assert removals(lines) == []


def test_dangling_images_are_left_to_docker_image_prune():
    lines = listing(("<none>:<none>", days_ago(9)))
    assert removals(lines) == []


def test_removals_are_ordered_oldest_first():
    """The script stops as soon as it is back under target, so the order is
    what decides which images survive."""
    lines = listing(
        ("muma/a:0.4.0", days_ago(4)),
        ("muma/a:0.3.0", days_ago(9)),
        ("muma/a:0.2.0", days_ago(40)),
        ("muma/a:0.1.0", days_ago(90)),
    )
    assert removals(lines, keep_versions=1) == [
        "muma/a:0.1.0",
        "muma/a:0.2.0",
        "muma/a:0.3.0",
    ]


def test_a_malformed_line_does_not_take_the_whole_sweep_down():
    """`docker images` output has changed format before; a janitor that raises
    on one odd line does nothing at all on a full disk."""
    lines = listing(("muma/a:0.1.0", days_ago(90)), ("muma/a:0.2.0", days_ago(80)))
    lines.insert(1, "garbage-without-tabs")
    lines.insert(2, "repo:tag\tnot-a-timestamp\tsha")
    assert removals(lines, keep_versions=1) == ["muma/a:0.1.0"]


def test_the_release_prefix_comes_from_the_docker_user():
    """Only the configured registry user's repositories are release images; another user's are not ours."""
    lines = listing(
        ("acme/music-manager:0.1.0", days_ago(399)),
        ("acme/music-manager:0.2.0", days_ago(398)),
        ("muma/music-manager:0.1.0", days_ago(399)),
        ("muma/music-manager:0.2.0", days_ago(398)),
    )
    assert removals(lines, keep_versions=1, docker_user="acme") == ["acme/music-manager:0.1.0"]
    assert removals(lines, keep_versions=1) == ["muma/music-manager:0.1.0"]


def test_without_a_docker_user_no_release_image_is_selected_but_ci_images_still_are():
    lines = listing(
        ("muma/music-manager:0.1.0", days_ago(399)),
        ("muma/music-manager:0.2.0", days_ago(398)),
        ("muma-ci/tools:1", days_ago(399)),
        ("muma-ci/tools:2", days_ago(398)),
    )
    assert removals(lines, keep_versions=1, docker_user="") == ["muma-ci/tools:1"]


def test_the_plan_warns_but_runs_without_a_docker_user():
    import os
    import subprocess

    env = {k: v for k, v in os.environ.items() if k != "DOCKER_USER"}
    result = subprocess.run(
        ["python3", str(MODULE_PATH)], input="", env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "DOCKER_USER" in result.stderr
