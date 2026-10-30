"""Behaviour of scripts/ci/release-version-check.sh.

The script is the only thing standing between "someone forgot to write release
notes" and a tagged production release, so it gets real tests: each one builds
a throw-away git repository with a develop and a master branch, checks out a
release or hotfix branch, and runs the script the way CI runs it.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "release-version-check.sh"


def _git_env() -> dict[str, str]:
    """The environment without GIT_* variables.

    Git runs the pre-commit hook with GIT_INDEX_FILE set, and this suite runs
    from that hook. Inherited, it makes `git add` in the throw-away repo write
    into the index of the commit being made (bug report 152).
    """
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=_git_env())


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
    gradle = origin / "services" / "muma-mobile" / "app"
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
    subprocess.run(["git", "clone", str(origin), str(clone)], check=True, capture_output=True, env=_git_env())
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
        check=False,
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
    no Android code at all. Measured against develop, services/muma-mobile
    "changed" while build.gradle did not, and the script rejects a hotfix that
    is entirely correct.
    """
    _git(repo, "checkout", "develop", "--quiet")
    queued = repo / "services" / "muma-mobile" / "app" / "Queued.kt"
    queued.write_text("// unreleased work, still only on develop\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "feat(muma-mobile): something not released yet", "--quiet")
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
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "CI_COMMIT_BRANCH": "release/0.0.2",
            "HOME": str(repo),
            "VERSION_CHECK_BASE": "origin/master",
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _merge_to_develop_then_cut(repo: Path, path: str, version: str) -> None:
    """Land an app change on develop, then cut release/<version> from it.

    This is the normal order: the change is merged before the release is cut, so
    a diff against develop shows nothing -- only a diff against master does.
    """
    _git(repo, "checkout", "develop", "--quiet")
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("// merged into develop before the cut\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "feat: an app change", "--quiet")
    _git(repo, "push", "origin", "develop", "--quiet")
    _git(repo, "checkout", "-b", f"release/{version}", "--quiet")


def _bump_app(repo: Path, code: int, name: str) -> None:
    gradle = repo / "services" / "muma-mobile" / "app" / "build.gradle"
    gradle.write_text(f'android {{ defaultConfig {{ versionCode {code}\nversionName "{name}" }} }}\n', encoding="utf-8")


@pytest.mark.parametrize(
    "path",
    ["services/frontend/src/lib/BpmView.svelte", "services/muma-mobile/app/src/Feature.kt"],
)
def test_an_app_change_merged_before_the_cut_requires_a_version_code_bump(repo: Path, path: str):
    """0.84.0 shipped a new web UI with the APK still at versionCode 352.

    The Capacitor shell serves the web bundle baked into the APK, so a frontend
    change is an app change; and both kinds reach the release branch through
    develop, where a diff against develop cannot see them.
    """
    _merge_to_develop_then_cut(repo, path, "0.1.0")
    _stabilise(repo, "0.1.0", "\n### Added\n- A feature.\n")
    result = _run(repo, "release/0.1.0")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "versionCode is still 1" in result.stdout


def test_an_app_change_passes_once_the_version_code_moved(repo: Path):
    _merge_to_develop_then_cut(repo, "services/frontend/src/lib/BpmView.svelte", "0.1.0")
    _bump_app(repo, 2, "0.0.2")
    _stabilise(repo, "0.1.0", "\n### Added\n- A feature.\n")
    result = _run(repo, "release/0.1.0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "versionCode moved (1 -> 2)" in result.stdout


def test_git_in_the_throw_away_repo_ignores_an_inherited_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Run from a pre-commit hook, the suite must not touch the hook's index."""
    hook_index = tmp_path / "hook-index"
    monkeypatch.setenv("GIT_INDEX_FILE", str(hook_index))
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _write(repo, "VERSION", "0.0.1\n")
    _git(repo, "add", "VERSION")
    assert not hook_index.exists()
    assert (repo / ".git" / "index").exists()
