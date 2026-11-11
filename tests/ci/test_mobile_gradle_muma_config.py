"""Gradle side of the Android build settings (issue #189, step 6).

Needs Docker and the Android CI image, so it runs only when MUMA_GRADLE_CONFIG_TEST=1 (the cases
are in scripts/test/muma-mobile-config-check.sh). The source-level checks always run.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "test" / "muma-mobile-config-check.sh"
GRADLE = ROOT / "services" / "muma-mobile" / "app" / "build.gradle"


def test_release_tasks_depend_on_the_config_check():
    text = GRADLE.read_text()
    assert 'tasks.register("checkMumaReleaseConfig")' in text
    assert "(assemble|bundle|package)Release" in text
    assert 'dependsOn "checkMumaReleaseConfig"' in text


def test_config_check_runs_in_the_mobile_unit_job():
    ci = (ROOT / ".gitlab-ci.yml").read_text()
    unit = ci[ci.index("\nmobile:unit:") :]
    unit = unit[: unit.index("after_script")]
    assert "./scripts/test/muma-mobile-config-check.sh" in unit


def test_values_are_validated_before_they_reach_buildconfig():
    assert "has an invalid value" in GRADLE.read_text()


@pytest.mark.skipif(os.environ.get("MUMA_GRADLE_CONFIG_TEST") != "1", reason="needs Docker and the Android image")
def test_gradle_config_cases():
    result = subprocess.run(["bash", str(CHECK)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def _run_with_fake_docker(tmp_path, gradle_output):
    """Run the check with a `docker` that has the image and answers every `run` with exit 1 and
    `gradle_output`, the way a refused Gradle build or a container that never started would."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(f'#!/bin/bash\n[ "$1" = image ] && exit 0\nprintf "%s\\n" {gradle_output!r}\nexit 1\n')
    docker.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "TMPDIR": str(tmp_path)}
    env.pop("CI_JOB_ID", None)
    return subprocess.run(["bash", str(CHECK)], capture_output=True, text=True, check=False, env=env)


def test_an_expect_fail_case_does_not_pass_when_gradle_never_starts(tmp_path):
    """A docker error exits non-zero too; without the expected message it is not the refusal (#196)."""
    result = _run_with_fake_docker(tmp_path, "docker: Error response from daemon: no such image")
    assert result.returncode != 0
    assert "ok: " not in result.stdout, result.stdout
    assert result.stdout.count("but not with:") == 4, result.stdout


def test_an_expect_fail_case_passes_on_the_message_it_names(tmp_path):
    output = (
        "A release build needs MUMA_SERVER_URL (not the example default)\n"
        "muma.serverUrl / MUMA_SERVER_URL has an invalid value\n"
        "muma.ownDomain / MUMA_OWN_DOMAIN has an invalid value"
    )
    result = _run_with_fake_docker(tmp_path, output)
    for label in (
        "release check fails without variables",
        "release check fails with the default server",
        "a quote in the value is refused",
        "a quote in the own domain is refused",
    ):
        assert f"ok: {label}" in result.stdout, result.stdout
    # The ok cases still need a zero exit, which this docker never gives.
    assert "FAILED: debug configures without variables (exit 1)" in result.stdout
