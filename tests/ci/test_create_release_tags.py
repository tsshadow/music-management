"""release:tag makes annotated tags with git under a neutral identity (issue #207).

The script is run in a scratch repository with a bare repository as the remote and a fake
``curl`` that says no tag exists yet.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "create-release-tags.sh"


def _git(cwd: Path, *args: str) -> str:
    """Run git in `cwd` and return its trimmed stdout."""
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_script_has_no_api_tag_create_and_sets_identity() -> None:
    """The POST to repository/tags is gone, and the identity is set on the git call."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--request POST" not in text
    assert "tag -a" in text
    assert "user.email=${TAGGER_EMAIL}" in text
    assert "GIT_COMMITTER_EMAIL=" in text


def test_tags_are_annotated_with_neutral_tagger(tmp_path: Path) -> None:
    """The pushed tag has the neutral tagger, the message and the target commit."""
    repo = tmp_path / "work"
    (repo / "scripts" / "ci").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "ci" / "create-release-tags.sh")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=x", "-c", "user.email=x@example.com", "commit", "-qm", "base")
    sha = _git(repo, "rev-parse", "HEAD")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text("#!/bin/bash\nexit 22\n", encoding="utf-8")
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "TAG_CREATION_TOKEN": "t",
        "CI_API_V4_URL": "https://gitlab.invalid/api/v4",
        "CI_PROJECT_ID": "7",
        "CI_COMMIT_SHA": sha,
        "TAG_PUSH_URL": str(remote),
        # CI images set these; they must not win over the neutral identity.
        "GIT_COMMITTER_NAME": "ci",
        "GIT_COMMITTER_EMAIL": "ci@localhost",
        "GIT_AUTHOR_NAME": "ci",
        "GIT_AUTHOR_EMAIL": "ci@localhost",
    }
    subprocess.run(["bash", "scripts/ci/create-release-tags.sh"], cwd=repo, env=env, check=True, capture_output=True)

    tag = "release-v9.9.9"
    assert _git(remote, "rev-parse", f"{tag}^{{commit}}") == sha
    assert _git(remote, "cat-file", "-t", tag) == "tag"
    body = _git(remote, "cat-file", "tag", tag)
    assert "tagger ci-release-tagging <ci-release-tagging@users.noreply.example.com>" in body
    assert "noreply.gitlab" not in body
    assert "Backend/monorepo release v9.9.9" in body
