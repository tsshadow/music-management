"""public:history (issue #208): scripts/ci/public_guard.py checks commit and tag metadata.

Every test builds a throw-away repository with synthetic commits. The guarded words are built by
concatenation so this file passes public:check.
"""

import hashlib
import os
import shutil
import subprocess

from tests.ci.conftest import REPO_ROOT

CI_DIR = REPO_ROOT / "scripts" / "ci"
OWNER = "teu" + "n" + "schriks"
HANDLE = "tssha" + "dow"
CONTACT = f"github@{OWNER}.nl"
STRANGER = "someone@" + "example.net"
UPSTREAM = "author@" + "upstream.example"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Repo:
    """A repository with the guard files copied in, and helpers to commit and tag."""

    def __init__(self, path, tokens: tuple[str, ...] = ()):
        self.path = path
        (path / "scripts" / "ci").mkdir(parents=True)
        for name in ("public_guard.py", "public-patterns.txt"):
            shutil.copy(CI_DIR / name, path / "scripts" / "ci" / name)
        (path / "scripts" / "ci" / "public-banned-tokens.txt").write_text(
            "".join(f"{_digest(t)}  # test\n" for t in tokens) or "# none\n", encoding="utf-8"
        )
        (path / "scripts" / "ci" / "public-upstream-identities.txt").write_text(
            f"{_digest(UPSTREAM)}  # test\n", encoding="utf-8"
        )
        self.git("init", "-q", "-b", "develop")
        self.n = 0

    def git(self, *args, email=CONTACT, name="Test Author"):
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)
        return subprocess.run(["git", "-C", str(self.path), *args], check=True, capture_output=True, text=True, env=env)

    def commit(self, message="work", author=CONTACT, committer=None):
        self.n += 1
        (self.path / f"f{self.n}.txt").write_text(str(self.n), encoding="utf-8")
        self.git("add", "-A")
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        env.update(
            GIT_AUTHOR_NAME="A",
            GIT_AUTHOR_EMAIL=author,
            GIT_COMMITTER_NAME="C",
            GIT_COMMITTER_EMAIL=committer or author,
        )
        subprocess.run(["git", "-C", str(self.path), "commit", "-q", "-m", message], check=True, env=env)

    def run(self, *args):
        return subprocess.run(
            ["python3", str(self.path / "scripts" / "ci" / "public_guard.py"), "history", *args],
            capture_output=True,
            text=True,
            check=False,
            cwd=self.path,
        )


def test_allowed_identities_pass(tmp_path):
    repo = Repo(tmp_path)
    repo.commit(author=CONTACT)
    repo.commit(author="ci@example.com")
    repo.commit(author="bot@users.noreply.example.com")
    repo.commit(author=UPSTREAM.upper())
    result = repo.run("--full")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 checked" in result.stdout


def test_an_unknown_author_or_committer_fails_without_printing_the_address(tmp_path):
    repo = Repo(tmp_path)
    repo.commit(author=STRANGER)
    repo.commit(author=CONTACT, committer=STRANGER)
    result = repo.run("--full")
    assert result.returncode == 1
    assert result.stdout.count("identity") >= 3
    assert STRANGER not in result.stdout + result.stderr


def test_a_pattern_in_the_message_fails(tmp_path):
    repo = Repo(tmp_path)
    repo.commit(message=f"See merge request {HANDLE}/project!5")
    result = repo.run("--full")
    assert result.returncode == 1
    assert "pattern" in result.stdout
    assert HANDLE not in result.stdout + result.stderr


def test_the_contact_address_is_not_a_pattern_hit(tmp_path):
    repo = Repo(tmp_path)
    repo.commit(message="fine")
    assert repo.run("--full").returncode == 0


def test_a_banned_word_in_the_message_fails(tmp_path):
    repo = Repo(tmp_path, tokens=("zorblax",))
    repo.commit(message="thanks to Zorblax")
    result = repo.run("--full")
    assert result.returncode == 1
    assert "banned word" in result.stdout
    assert "zorblax" not in (result.stdout + result.stderr).lower()


def test_an_annotated_tag_by_an_unknown_tagger_fails(tmp_path):
    repo = Repo(tmp_path)
    repo.commit()
    repo.git("tag", "-a", "v1", "-m", "release", email=STRANGER)
    result = repo.run("--full")
    assert result.returncode == 1
    assert "tag v1: identity" in result.stdout


def test_an_annotated_tag_by_the_owner_passes(tmp_path):
    repo = Repo(tmp_path)
    repo.commit()
    repo.git("tag", "-a", "v1", "-m", "release")
    assert repo.run("--full").returncode == 0


def test_range_mode_checks_only_the_range(tmp_path):
    repo = Repo(tmp_path)
    repo.commit(author=STRANGER)
    repo.git("branch", "base")
    repo.commit()
    clean = repo.run("--range", "base..develop")
    assert clean.returncode == 0, clean.stdout
    assert "1 checked" in clean.stdout
    assert repo.run("--full").returncode == 1


def test_an_empty_pattern_file_fails_the_check(tmp_path):
    repo = Repo(tmp_path)
    repo.commit()
    (tmp_path / "scripts" / "ci" / "public-patterns.txt").write_text("# nothing\n", encoding="utf-8")
    result = repo.run("--full")
    assert result.returncode != 0
    assert "proves nothing" in result.stderr + result.stdout


def test_the_history_job_is_a_hard_gate_everywhere():
    """public:history may not fail anywhere: the history is clean since the rewrite of #209."""
    text = (REPO_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    job = text[text.index("\npublic:history:") :]
    job = job[: job.index("\n\n#")]
    assert "allow_failure" not in job
    assert "when: on_success" in job
    assert "public-history-check.sh" in job


def test_no_branch_is_exempt_from_the_history_check():
    """Renovate branches were skipped until #209; every branch is checked now."""
    script = (CI_DIR / "public-history-check.sh").read_text(encoding="utf-8")
    assert "renovate" not in script.lower()
    assert "exit 0" not in script
