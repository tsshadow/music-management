"""The Android CI image tag separates users, so a local build cannot break the runner's jobs."""

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_tag_carries_the_uid_that_builds_the_image(tmp_path: Path) -> None:
    """A stub docker reports the image as present; the script exports a tag with this uid."""
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\nexit 0\n")
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}

    result = subprocess.run(
        ["bash", "-c", f'source "{ROOT}/scripts/ci/android-image.sh"; printf %s "$ANDROID_CI_IMAGE"'],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.endswith(f"-uid{os.getuid()}")
