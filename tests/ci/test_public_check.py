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

OWNER = "teu" + "n" + "schriks"
HANDLE = "tssha" + "dow"
# Written reversed: a banned word must not sit in the source either.
PARTNER = "leppaslohtesil"[::-1]
LAN = "192." + "168."
LOGIN = "teu" + "n"
EMPLOYER = "mob" + "a"

FORBIDDEN = {
    "owner domain": f"see https://{OWNER}.nl/x",
    "owner host": f"https://muma.{OWNER}.nl/api",
    "handle": f"git clone {HANDLE}/repo",
    "partner name": "from " + PARTNER,
    "oauth project": "7144609033" + "1-abc.apps.googleusercontent.com",
    "password manager": "the " + "vaultwar" + "den host",
    "lan host": f"ssh root@{LAN}1.40",
    "owner domain as package suffix": f"https://{OWNER}.mumamobile.com/x",
    "owner domain after package id": f"nl.{OWNER}.mumamobile.evil.nl and {OWNER}.nl",
    "contact lookalike": f"github@{OWNER}.nl.evil.com",
    "private block with suffix": f"x = {LAN}0.0/160",
    "old personal host upper case": "curl https://SPOTI" + "FY.example.org/rest",
    "lan host other subnet": f"ping {LAN}0.27",
    "old personal host": "curl https://spoti" + "fy.example.org/rest",
    "owner login in a query": f"/rest/ping.view?u={LOGIN}&p=x",
    "owner login as home directory": f"/home/{LOGIN}/Music",
    "employer": f"made at {EMPLOYER}",
    "employer upper case": f"{EMPLOYER.upper()} icons",
    "employer home directory": f"/home/{EMPLOYER}/git",
}

ALLOWED = {
    "android package": f"nl.{OWNER}.mumamobile",
    "android package path": f"src/main/kotlin/nl/{OWNER}/mumamobile/Foo.kt",
    "contact address": f"github@{OWNER}.nl",
    "private block": f"trusted = {LAN}0.0/16",
    "spotify api": "https://api.spoti" + "fy.com/v1/search",
    "spotify source": "Spoti" + "fy.cpp",
    "spotify attribute access": "spoti" + "fy.SpotifyArtistImageProvider.SEARCH_URL",
    "spotify provider path": "providers/spoti" + "fy.py",
    "capitalised first name": "Copyright (C) 2026 " + LOGIN.capitalize() + " Schriks",
    "login inside a longer word": f"x{LOGIN}y and {LOGIN}2 and {LOGIN}_a",
    "employer inside a longer word": f"{EMPLOYER}xterm and auto{EMPLOYER}",
}


def _run(tmp_path, files: dict[str, str], patterns: str | None = None, extra_env: dict[str, str] | None = None):
    """Make a git repository with `files`, run public-check.sh there and return the process."""
    repo = tmp_path / "repo"
    (repo / "scripts" / "ci").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "ci" / "public-check.sh")
    shutil.copy(PATTERNS, repo / "scripts" / "ci" / "public-patterns.txt")
    if patterns is not None:
        (repo / "scripts" / "ci" / "public-patterns.txt").write_text(patterns, encoding="utf-8")
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    env = {**os.environ, "PUBLIC_CHECK_SKIP_GITLEAKS": "1", **(extra_env or {})}
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
    for word in (OWNER, HANDLE, PARTNER, EMPLOYER, "7144609033" + "1", "vaultwar" + "den", LAN + "1."):
        assert word not in text


def test_a_broken_pattern_file_fails_the_check(tmp_path):
    result = _run(tmp_path, {"doc.md": "nothing here"}, patterns="(unclosed\n")
    assert result.returncode != 0, result.stdout
    assert "proves nothing" in result.stderr


def test_an_empty_pattern_file_fails_the_check(tmp_path):
    result = _run(tmp_path, {"doc.md": "nothing here"}, patterns="# only a comment\n")
    assert result.returncode != 0, result.stdout


def test_missing_docker_fails_in_ci_and_warns_locally(tmp_path):
    """Without docker gitleaks cannot run: CI must not pass silently, a workstation may."""
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    for tool in ("bash", "git", "grep", "mktemp", "rm", "dirname"):
        found = shutil.which(tool)
        assert found
        (empty_bin / tool).symlink_to(found)
    base = {"PATH": str(empty_bin), "PUBLIC_CHECK_SKIP_GITLEAKS": "0"}
    in_ci = _run(tmp_path / "a", {"doc.md": "ok"}, extra_env={**base, "CI": "true"})
    assert in_ci.returncode == 1, in_ci.stdout
    local = _run(tmp_path / "b", {"doc.md": "ok"}, extra_env={**base, "CI": ""})
    assert local.returncode == 0, local.stdout + local.stderr
