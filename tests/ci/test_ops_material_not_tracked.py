"""Operations and agent material lives in the private repository muma/muma-ops.

Issue #189 step 8a. A checkout may hold these paths as symlinks made by muma-ops/install.sh;
git must never track them, or the public history carries hosts, runbooks and agent plans again.
"""

import subprocess

from tests.ci.conftest import REPO_ROOT

MOVED_PATHS = [
    ".claude",
    ".ai",
    ".junie",
    "scripts/prod",
    "scripts/crash-triage",
    "scripts/nightly-prod-check",
    "scripts/ssh",
    "scripts/vw.sh",
    "services/music-management-server/scripts/remote-build.sh",
    "docs/superpowers",
    "AGENTS.local.md",
]


def _git(*args: str) -> str:
    """Run git in the repository and return its stdout."""
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=True).stdout


def test_no_moved_path_is_tracked():
    tracked = _git("ls-files", "--", *MOVED_PATHS).splitlines()
    assert not tracked, "tracked again, belongs in muma/muma-ops:\n" + "\n".join(tracked[:20])


def test_every_moved_path_is_ignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    missing = [p for p in MOVED_PATHS if f"/{p}" not in gitignore]
    assert not missing, f"not in .gitignore: {missing}"


def test_claude_worktrees_stay_ignored():
    result = subprocess.run(["git", "-C", str(REPO_ROOT), "check-ignore", "-q", ".claude/worktrees/x"], check=False)
    assert result.returncode == 0
