"""scripts/dev.sh reads the optional owner-local .production file; a missing file or line must not stop it."""

import re
import subprocess

from tests.ci.conftest import REPO_ROOT


def _snippet() -> str:
    """The .production block of dev.sh up to and including the DOCKER_USER default."""
    text = (REPO_ROOT / "scripts" / "dev.sh").read_text(encoding="utf-8")
    match = re.search(r'PROD_FILE=.*?export DOCKER_USER="\$\{DOCKER_USER:-muma\}"', text, re.DOTALL)
    assert match, "the .production block of dev.sh changed shape"
    return match.group(0)


def _run(tmp_path, content):
    """Run the block under dev.sh's own `set -e` and return DOCKER_USER."""
    if content is not None:
        (tmp_path / ".production").write_text(content, encoding="utf-8")
    script = f'set -eo pipefail\nPROJECT_ROOT="{tmp_path}"\n{_snippet()}\necho "$DOCKER_USER"\n'
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_missing_file_gives_default(tmp_path):
    assert _run(tmp_path, None) == "muma"


def test_file_without_the_line_gives_default(tmp_path):
    assert _run(tmp_path, "Host: example\n") == "muma"


def test_file_with_the_line_is_used(tmp_path):
    assert _run(tmp_path, "Docker Hub User: someone\n") == "someone"
