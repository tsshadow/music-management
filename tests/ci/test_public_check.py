"""public:check (issue #189 step 10): scripts/ci/public-check.sh finds personal data in tracked files.

The forbidden words are built by concatenation so this file passes the check it tests.
"""

import hashlib
import os
import shutil
import subprocess

import pytest

from tests.ci.conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "ci" / "public-check.sh"
PATTERNS = REPO_ROOT / "scripts" / "ci" / "public-patterns.txt"
GUARD = REPO_ROOT / "scripts" / "ci" / "public_guard.py"
TOKENS = REPO_ROOT / "scripts" / "ci" / "public-banned-tokens.txt"

# sha256 of the guarded tokens (the partner's name and account, the employer, the OAuth project number).
# The words themselves are not in the repository.
SHIPPED_DIGESTS = {
    "25becee34cc33552d364365b7f5e698b1831ab6b2c57f33a286098f916085be3",
    "3b9e72334ed1a154b98fb44db70a003593a298a0132ec0f8658cd776963cd404",
    "498c6a5adc6b5ff2697e5c8da76be74f7db99e6928d8ec2ca089056fc2aae814",
    "354b7f0dd51bffa4f09b194094cce530310e98daf0d94c5f863853e7e0e57d5e",
    "e146dc555631f2903b75ea79bb3f037056af198f348ac6262941686c6bc7102a",
}

OWNER = "teu" + "n" + "schriks"
HANDLE = "tssha" + "dow"
LAN = "192." + "168."
LOGIN = "teu" + "n"

FORBIDDEN = {
    "owner domain": f"see https://{OWNER}.nl/x",
    "owner host": f"https://muma.{OWNER}.nl/api",
    "handle": f"git clone {HANDLE}/repo",
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
}


def _run(
    tmp_path,
    files: dict[str, str],
    patterns: str | None = None,
    tokens: str | None = None,
    extra_env: dict[str, str] | None = None,
):
    """Make a git repository with `files`, run public-check.sh there and return the process."""
    repo = tmp_path / "repo"
    (repo / "scripts" / "ci").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "ci" / "public-check.sh")
    shutil.copy(PATTERNS, repo / "scripts" / "ci" / "public-patterns.txt")
    shutil.copy(GUARD, repo / "scripts" / "ci" / "public_guard.py")
    shutil.copy(TOKENS, repo / "scripts" / "ci" / "public-banned-tokens.txt")
    if tokens is not None:
        (repo / "scripts" / "ci" / "public-banned-tokens.txt").write_text(tokens, encoding="utf-8")
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


def test_sql_files_are_scanned_too(tmp_path):
    result = _run(tmp_path, {"seed.sql": f"-- {HANDLE}"})
    assert result.returncode == 1, result.stdout


def test_patterns_file_names_no_forbidden_word():
    text = PATTERNS.read_text(encoding="utf-8").lower()
    for word in (OWNER, HANDLE, "vaultwar" + "den", LAN + "1."):
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
    for tool in ("bash", "git", "grep", "mktemp", "rm", "dirname", "python3"):
        found = shutil.which(tool)
        assert found
        (empty_bin / tool).symlink_to(found)
    base = {"PATH": str(empty_bin), "PUBLIC_CHECK_SKIP_GITLEAKS": "0"}
    in_ci = _run(tmp_path / "a", {"doc.md": "ok"}, extra_env={**base, "CI": "true"})
    assert in_ci.returncode == 1, in_ci.stdout
    local = _run(tmp_path / "b", {"doc.md": "ok"}, extra_env={**base, "CI": ""})
    assert local.returncode == 0, local.stdout + local.stderr


def _digest_file(*words: str) -> str:
    """Return the text of a banned-token file that lists the sha256 of each word."""
    return "".join(f"{hashlib.sha256(w.encode()).hexdigest()}  # test token\n" for w in words)


def test_a_banned_token_in_a_tracked_file_is_caught(tmp_path):
    """A whole word with a listed digest fails, whatever its case; a longer word that contains it passes."""
    tokens = _digest_file("zorblax")
    hit = _run(tmp_path / "a", {"doc.md": "made by Zorblax today"}, tokens=tokens)
    assert hit.returncode == 1, hit.stdout
    assert "doc.md" in hit.stdout
    assert "zorblax" not in (hit.stdout + hit.stderr).lower()
    longer = _run(tmp_path / "b", {"doc.md": "zorblaxterm and autozorblax"}, tokens=tokens)
    assert longer.returncode == 0, longer.stdout


def test_the_shipped_token_list_holds_the_guarded_digests():
    """The partner, the employer and the OAuth project number stay guarded, without their plain text."""
    listed = {
        line.split()[0]
        for line in TOKENS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert listed >= SHIPPED_DIGESTS
