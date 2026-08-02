"""Behaviour of scripts/ci/release-version-check.sh.

The script is the only thing standing between "someone forgot to write release
notes" and a tagged production release, so it gets real tests: each one builds
a throw-away git repository with a develop and a master branch, checks out a
release or hotfix branch, and runs the script the way CI runs it.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "release-version-check.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _write(repo: Path, name: str, body: str) -> None:
    (repo / name).write_text(body, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with develop and master at 0.0.1, and an `origin` remote."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-b", "develop", "--quiet")
    _git(origin, "config", "user.email", "ci@example.com")
    _git(origin, "config", "user.name", "CI")
    _write(origin, "VERSION", "0.0.1\n")
    _write(origin, "CHANGELOG.md", "# Changelog\n\n## [Unreleased]\n")
    _write(origin, "RELEASE_NOTES.md", "# Release notes\n")
    gradle = origin / "services" / "ultrasonic" / "ultrasonic"
    gradle.mkdir(parents=True)
    (gradle / "build.gradle").write_text(
        'android { defaultConfig { versionCode 1\nversionName "0.0.1" } }\n',
        encoding="utf-8",
    )
    _git(origin, "add", ".")
    _git(origin, "commit", "-m", "initial", "--quiet")
    _git(origin, "branch", "master")
    # Pushing to a checked-out branch is refused by default; this repo only
    # ever serves as a remote.
    _git(origin, "config", "receive.denyCurrentBranch", "ignore")

    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", str(origin), str(clone)], check=True, capture_output=True
    )
    _git(clone, "config", "user.email", "ci@example.com")
    _git(clone, "config", "user.name", "CI")
    return clone


def _copy_script(repo: Path) -> Path:
    """Put the real script inside `repo` and return its path.

    The script derives its own ROOT_DIR from $BASH_SOURCE and cd's there, so
    running it from the source tree would check *this* repository no matter
    what cwd it was given. Copying it into the throw-away repo at the same
    relative path is what makes it look at the repo under test.
    """
    target = repo / "scripts" / "ci" / SCRIPT.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(SCRIPT.read_bytes())
    return target


def _run(repo: Path, branch: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_copy_script(repo))],
        cwd=repo,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "CI_COMMIT_BRANCH": branch, "HOME": str(repo)},
    )


def _stabilise(repo: Path, version: str, changelog_body: str) -> None:
    _write(repo, "VERSION", f"{version}\n")
    _write(
        repo,
        "CHANGELOG.md",
        f"# Changelog\n\n## [Unreleased]\n\n## [{version}] - 2026-08-02\n{changelog_body}",
    )
    _write(repo, "RELEASE_NOTES.md", f"# Release notes\n\n## {version}\nSomething shipped.\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", f"chore(release): stabilize {version}", "--quiet")


def test_release_branch_passes_when_everything_was_updated(repo: Path):
    _git(repo, "checkout", "-b", "release/0.0.2", "--quiet")
    _stabilise(repo, "0.0.2", "\n### Fixed\n- A bug.\n")
    result = _run(repo, "release/0.0.2")
    assert result.returncode == 0, result.stdout + result.stderr


def test_release_branch_fails_when_version_was_not_bumped(repo: Path):
    _git(repo, "checkout", "-b", "release/0.0.2", "--quiet")
    _write(repo, "CHANGELOG.md", "# Changelog\n\n## [0.0.1] - 2026-08-02\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "chore: changelog only", "--quiet")
    result = _run(repo, "release/0.0.2")
    assert result.returncode != 0
    assert "VERSION was not bumped" in result.stdout


def test_hotfix_branch_compares_against_master(repo: Path):
    """A hotfix is cut from master, so develop is the wrong "before" picture.

    Here develop carries an unreleased Ultrasonic change and the hotfix touches
    no Android code at all. Measured against develop, services/ultrasonic
    "changed" while build.gradle did not, and the script rejects a hotfix that
    is entirely correct.
    """
    _git(repo, "checkout", "develop", "--quiet")
    queued = repo / "services" / "ultrasonic" / "ultrasonic" / "Queued.kt"
    queued.write_text("// unreleased work, still only on develop\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "feat(ultrasonic): something not released yet", "--quiet")
    _git(repo, "push", "origin", "develop", "--quiet")

    _git(repo, "checkout", "master", "--quiet")
    _git(repo, "checkout", "-b", "hotfix/0.0.2", "--quiet")
    _stabilise(repo, "0.0.2", "\n### Fixed\n- An urgent bug.\n")

    result = _run(repo, "hotfix/0.0.2")
    assert result.returncode == 0, result.stdout + result.stderr


def test_added_section_requires_a_minor_bump(repo: Path):
    """0.0.59 after 47 patch bumps tells nobody anything. A release with an
    ### Added section is a feature release and must say so in the number."""
    _git(repo, "checkout", "-b", "release/0.0.2", "--quiet")
    _stabilise(repo, "0.0.2", "\n### Added\n- A whole new feature.\n")
    result = _run(repo, "release/0.0.2")
    assert result.returncode != 0
    assert "minor" in result.stdout


def test_added_section_passes_with_a_minor_bump(repo: Path):
    _git(repo, "checkout", "-b", "release/0.1.0", "--quiet")
    _stabilise(repo, "0.1.0", "\n### Added\n- A whole new feature.\n")
    result = _run(repo, "release/0.1.0")
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_minor_bump_must_reset_the_patch(repo: Path):
    _git(repo, "checkout", "-b", "release/0.1.3", "--quiet")
    _stabilise(repo, "0.1.3", "\n### Added\n- A whole new feature.\n")
    result = _run(repo, "release/0.1.3")
    assert result.returncode != 0
    assert "0.1.0" in result.stdout


def test_fix_only_release_may_bump_the_patch(repo: Path):
    _git(repo, "checkout", "-b", "release/0.0.2", "--quiet")
    _stabilise(repo, "0.0.2", "\n### Fixed\n- A bug.\n")
    result = _run(repo, "release/0.0.2")
    assert result.returncode == 0, result.stdout + result.stderr


def test_an_added_section_for_another_release_does_not_count(repo: Path):
    """Only the section belonging to *this* version decides the rule; the
    changelog keeps every previous release's ### Added forever."""
    _git(repo, "checkout", "-b", "release/0.0.2", "--quiet")
    _write(repo, "VERSION", "0.0.2\n")
    _write(
        repo,
        "CHANGELOG.md",
        "# Changelog\n\n## [Unreleased]\n\n"
        "## [0.0.2] - 2026-08-02\n\n### Fixed\n- A bug.\n\n"
        "## [0.0.1] - 2026-07-01\n\n### Added\n- The whole application.\n",
    )
    _write(repo, "RELEASE_NOTES.md", "# Release notes\n\n## 0.0.2\nA fix.\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "chore(release): stabilize 0.0.2", "--quiet")
    result = _run(repo, "release/0.0.2")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_comparison_base_can_be_overridden(repo: Path):
    """CI never sets it, but it is what makes the base visible in a failure."""
    _git(repo, "checkout", "-b", "release/0.0.2", "--quiet")
    _stabilise(repo, "0.0.2", "\n### Fixed\n- A bug.\n")
    result = subprocess.run(
        ["bash", str(_copy_script(repo))],
        cwd=repo,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "CI_COMMIT_BRANCH": "release/0.0.2",
            "HOME": str(repo),
            "VERSION_CHECK_BASE": "origin/master",
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
