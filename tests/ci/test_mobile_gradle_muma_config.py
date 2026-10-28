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


def test_values_are_validated_before_they_reach_buildconfig():
    assert "has an invalid value" in GRADLE.read_text()


@pytest.mark.skipif(os.environ.get("MUMA_GRADLE_CONFIG_TEST") != "1", reason="needs Docker and the Android image")
def test_gradle_config_cases():
    result = subprocess.run(["bash", str(CHECK)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
