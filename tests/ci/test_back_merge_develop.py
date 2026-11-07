"""release:back-merge-develop merges master into develop with git under a neutral identity.

Through the API, GitLab wrote the merge commit as the token's bot user, whose address names the
private GitLab host, and public:history failed on each one. The script runs here in a scratch
repository with a bare repository as the remote.
"""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "back-merge-develop.sh"
NEUTRAL = "ci-release-tagging <ci-release-tagging@users.noreply.example.com>"


def _git(cwd: Path, *args: str) -> str:
    """Run git in `cwd` and return its trimmed stdout."""
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _commit(repo: Path, name: str, text: str) -> str:
    """Write `name` and commit it as a throwaway author. Return the new commit id."""
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "-c", "user.name=x", "-c", "user.email=x@example.com", "commit", "-qm", name)
    return _git(repo, "rev-parse", "HEAD")


def _setup(tmp_path: Path, conflict: bool = False) -> tuple[Path, Path, str]:
    """A remote with develop and master that went apart. Return the clone, the remote and master."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    repo = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "develop", str(repo)], check=True)
    (repo / "scripts" / "ci").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "ci" / "back-merge-develop.sh")
    _commit(repo, "VERSION", "1.0.0\n")
    _git(repo, "checkout", "-q", "-b", "master")
    master = _commit(repo, "VERSION", "1.0.1\n")
    _git(repo, "checkout", "-q", "develop")
    _commit(repo, "VERSION" if conflict else "feature.txt", "2.0.0\n")
    _git(repo, "push", "-q", str(remote), "develop", "master")
    _git(repo, "checkout", "-q", "--detach", master)
    return repo, remote, master


def _run(repo: Path, remote: Path, master: str) -> subprocess.CompletedProcess:
    """Run the script as the master pipeline would, with CI's own identity in the environment."""
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(repo.parent),
        "TAG_CREATION_TOKEN": "unused",
        "CI_COMMIT_SHA": master,
        "BACKMERGE_PUSH_URL": str(remote),
        # CI images set these; they must not win over the neutral identity.
        "GIT_COMMITTER_NAME": "ci",
        "GIT_COMMITTER_EMAIL": "ci@localhost",
        "GIT_AUTHOR_NAME": "ci",
        "GIT_AUTHOR_EMAIL": "ci@localhost",
    }
    return subprocess.run(
        ["bash", "scripts/ci/back-merge-develop.sh"], cwd=repo, env=env, capture_output=True, text=True
    )


def test_the_merge_commit_has_the_neutral_identity(tmp_path: Path) -> None:
    """develop gets one merge commit, by the neutral identity, with master as its second parent."""
    repo, remote, master = _setup(tmp_path)

    result = _run(repo, remote, master)

    assert result.returncode == 0, result.stdout + result.stderr
    head = _git(remote, "cat-file", "commit", "develop")
    assert f"author {NEUTRAL}" in head
    assert f"committer {NEUTRAL}" in head
    assert "noreply.gitlab" not in head
    assert _git(remote, "rev-parse", "develop^2") == master
    assert "Merge branch 'master' into 'develop'" in head


def test_a_develop_that_has_master_gets_no_commit(tmp_path: Path) -> None:
    """A second run, after a retried pipeline, changes nothing."""
    repo, remote, master = _setup(tmp_path)
    _run(repo, remote, master)
    before = _git(remote, "rev-parse", "develop")

    result = _run(repo, remote, master)

    assert result.returncode == 0
    assert "nothing to back-merge" in result.stdout
    assert _git(remote, "rev-parse", "develop") == before


def test_a_conflict_fails_and_leaves_develop_alone(tmp_path: Path) -> None:
    """A conflict needs a person: the job fails and develop does not move."""
    repo, remote, master = _setup(tmp_path, conflict=True)
    before = _git(remote, "rev-parse", "develop")

    result = _run(repo, remote, master)

    assert result.returncode == 1
    assert "conflict" in result.stdout
    assert _git(remote, "rev-parse", "develop") == before


def test_the_script_does_not_merge_through_the_api() -> None:
    """No merge request and no merge call: GitLab would write the commit as the bot."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "merge_requests" not in text
    assert "GIT_COMMITTER_EMAIL=" in text
