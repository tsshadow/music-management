"""public:check (issue #189 step 10): scripts/ci/public-check.sh finds personal data in tracked files.

The forbidden words are built by concatenation so this file passes the check it tests.
"""

import os
import shutil
import subprocess

import pytest

from tests.ci.conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "ci" / "public-check.sh"
PATTERNS = REPO_ROOT / "scripts" / "ci" / "public-patterns.txt"

OWNER = "user" + "schriks"
HANDLE = "tssha" + "dow"
LAN = "192." + "168."

FORBIDDEN = {
    "owner domain": f"see https://{OWNER}.nl/x",
    "owner host": f"https://muma.{OWNER}.nl/api",
    "handle": f"git clone {HANDLE}/repo",
    "partner name": "from " + "lisetholsappe" + "l",
    "oauth project": "7144609033" + "1-abc.apps.googleusercontent.com",
    "password manager": "the " + "vaultwar" + "den host",
    "lan host": f"ssh root@{LAN}1.40",
    "lan host other subnet": f"ping {LAN}0.27",
    "old personal host": "curl https://spoti" + "fy.example.org/rest",
}

ALLOWED = {
    "android package": f"nl.{OWNER}.mumamobile",
    "android package path": f"src/main/kotlin/nl/{OWNER}/mumamobile/Foo.kt",
    "contact address": f"github@{OWNER}.nl",
    "private block": f"trusted = {LAN}0.0/16",
    "spotify api": "https://api.spoti" + "fy.com/v1/search",
    "spotify source": "Spoti" + "fy.cpp",
    "spotify provider path": "providers/spoti" + "fy.py",
}


def _run(tmp_path, files: dict[str, str]):
    """Make a git repository with `files`, run public-check.sh there and return the process."""
    repo = tmp_path / "repo"
    (repo / "scripts" / "ci").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "ci" / "public-check.sh")
    shutil.copy(PATTERNS, repo / "scripts" / "ci" / "public-patterns.txt")
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    env = {**os.environ, "PUBLIC_CHECK_SKIP_GITLEAKS": "1"}
    return subprocess.run(
        ["bash", str(repo / "scripts" / "ci" / "public-check.sh")], capture_output=True, text=True, env=env, check=False
    )


@pytest.mark.parametrize("label", sorted(FORBIDDEN))
def test_forbidden_form_is_caught(tmp_path, label):
    result = _run(tmp_path, {"doc.md": FORBIDDEN[label]})
    assert result.returncode == 1, result.stdout
    assert "doc.md:1" in result.stdout


@pytest.mark.parametrize("label", sorted(ALLOWED))
def test_allowed_form_passes(tmp_path, label):
    result = _run(tmp_path, {"doc.md": ALLOWED[label]})
    assert result.returncode == 0, result.stdout


def test_migrations_are_not_scanned(tmp_path):
    result = _run(tmp_path, {"migrate_v1.sql": f"-- {HANDLE}"})
    assert result.returncode == 0, result.stdout


def test_patterns_file_names_no_forbidden_word():
    text = PATTERNS.read_text(encoding="utf-8").lower()
    for word in (OWNER, HANDLE, "someuser"[:-1] + "l", "7144609033" + "1", "vaultwar" + "den", LAN + "1."):
        assert word not in text
