"""The production host key is pinned, never accepted blindly.

Every deploy and verify script used to connect with StrictHostKeyChecking=no
after appending whatever ssh-keyscan returned to the runner's known_hosts, so
anything answering on the production address got the root key's signature,
the production env file on stdin and the migrations
(docs/bug-reports/081-compose-logs-grow-without-bound.md).
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "lib" / "ssh_host_keys.sh"
HOST = "203.0.113.9"
PROD_SSH_SETUP = ROOT / "scripts" / "ci" / "prod-ssh-setup.sh"
SSH_SCRIPTS = [
    ROOT / "scripts" / "deploy.sh",
    ROOT / "scripts" / "ci-deploy.sh",
    PROD_SSH_SETUP,
    ROOT / "scripts" / "ci" / "post-deploy-verify.sh",
    ROOT / "scripts" / "ci" / "verify-prod-version.sh",
    ROOT / "services" / "music-management-server" / "scripts" / "deploy-stack.sh",
]


@pytest.fixture
def pinned(tmp_path: Path) -> Path:
    """A known_hosts file that lists HOST, with a key generated for the test."""
    if not shutil.which("ssh-keygen"):
        pytest.skip("needs ssh-keygen")
    key = tmp_path / "key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    public = key.with_suffix(".pub").read_text(encoding="utf-8").split()
    path = tmp_path / "known_hosts"
    path.write_text(f"{HOST} {public[0]} {public[1]}\n", encoding="utf-8")
    return path


def _code_lines(path: Path) -> list[str]:
    """The lines of a shell script that are not comments."""
    return [line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")]


def _opts(host: str, pinned: Path) -> list[str]:
    """What ssh_host_key_opts prints for HOST, as a list of arguments."""
    result = subprocess.run(
        ["bash", "-c", '. "$1"; ssh_host_key_opts "$2"', "_", str(LIB), host],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": "/usr/bin:/bin", "SSH_PINNED_KNOWN_HOSTS": str(pinned)},
    )
    return result.stdout.splitlines()


@pytest.mark.parametrize("path", SSH_SCRIPTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_production_ssh_call_disables_host_key_checking(path: Path):
    for line in _code_lines(path):
        assert "StrictHostKeyChecking=no" not in line, f"{path.name}: {line.strip()}"


def test_the_ci_setup_no_longer_learns_the_key_from_ssh_keyscan():
    assert not any("ssh-keyscan" in line for line in _code_lines(PROD_SSH_SETUP))


def test_the_ci_setup_has_no_default_production_host():
    """A missing PROD_REMOTE_HOST stops the job and names the variable; nothing is guessed."""
    assert not re.search(r"PROD_REMOTE_HOST:-[^}]", PROD_SSH_SETUP.read_text(encoding="utf-8"))
    result = subprocess.run(
        ["bash", "-c", '. "$1"; echo reached', "_", str(PROD_SSH_SETUP)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "SSH_PRIVATE_KEY": "unused"},
    )
    assert result.returncode == 1
    assert "PROD_REMOTE_HOST" in result.stderr
    assert "reached" not in result.stdout


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="needs ssh-keygen")
def test_a_pinned_host_is_checked_strictly_against_the_pinned_file_only(pinned: Path):
    assert _opts(HOST, pinned) == [
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={pinned}",
    ]


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="needs ssh-keygen")
def test_an_unpinned_host_learns_once_and_refuses_a_changed_key(pinned: Path):
    assert _opts("portainer.example.invalid", pinned) == ["-o", "StrictHostKeyChecking=accept-new"]


def test_a_missing_pinned_file_never_means_accept_anything(tmp_path: Path):
    assert _opts(HOST, tmp_path / "absent") == ["-o", "StrictHostKeyChecking=accept-new"]


def _into(env_extra: dict[str, str], pinned: Path | None, host: str = HOST):
    """Run ssh_host_key_opts_into the way a pipeline script does; return (status, options, stderr)."""
    env = {"PATH": "/usr/bin:/bin", **env_extra}
    if pinned is not None:
        env["PROD_SSH_KNOWN_HOSTS"] = str(pinned)
    script = '. "$1"; ssh_host_key_opts_into OPTS "$2" || exit 7; printf "%s\\n" "${OPTS[@]}"'
    result = subprocess.run(["bash", "-c", script, "_", str(LIB), host], capture_output=True, text=True, env=env)
    return result.returncode, result.stdout.splitlines(), result.stderr


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="needs ssh-keygen")
class TestPipelineFailsClosed:
    """With CI set, a host that is not pinned stops the script instead of being learned."""

    def test_a_missing_file_stops(self, tmp_path: Path):
        status, _, err = _into({"CI": "1"}, tmp_path / "absent")
        assert status == 7 and "PROD_SSH_KNOWN_HOSTS" in err

    def test_an_empty_file_stops(self, tmp_path: Path):
        empty = tmp_path / "known_hosts"
        empty.write_text("", encoding="utf-8")
        assert _into({"CI": "1"}, empty)[0] == 7

    def test_a_file_without_the_host_stops(self, pinned: Path):
        assert _into({"CI": "1"}, pinned, "198.51.100.7")[0] == 7

    def test_a_file_with_the_host_pins_it(self, pinned: Path):
        status, opts, _ = _into({"CI": "1"}, pinned)
        assert status == 0
        assert opts == ["-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={pinned}"]

    def test_the_opt_in_variable_allows_accept_new(self, tmp_path: Path):
        status, opts, _ = _into({"CI": "1", "PROD_SSH_ACCEPT_NEW_HOST_KEY": "true"}, tmp_path / "absent")
        assert status == 0 and opts == ["-o", "StrictHostKeyChecking=accept-new"]

    def test_outside_a_pipeline_an_unpinned_host_still_falls_back(self, tmp_path: Path):
        status, opts, _ = _into({}, tmp_path / "absent")
        assert status == 0 and opts == ["-o", "StrictHostKeyChecking=accept-new"]

    def test_prod_ssh_setup_stops_in_a_pipeline_without_the_file(self, tmp_path: Path):
        """The real script, with a fake ssh-add so only the host key decides."""
        fake = tmp_path / "bin"
        fake.mkdir()
        (fake / "ssh-add").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (fake / "ssh-add").chmod(0o755)
        key = tmp_path / "id"
        key.write_text("x\n", encoding="utf-8")
        env = {
            "PATH": f"{fake}:/usr/bin:/bin",
            "CI": "1",
            "SSH_PRIVATE_KEY": str(key),
            "SSH_AUTH_SOCK": "/nonexistent",
            "PROD_REMOTE_HOST": HOST,
            "PROD_SSH_KNOWN_HOSTS": str(tmp_path / "absent"),
        }
        result = subprocess.run(["bash", str(PROD_SSH_SETUP)], capture_output=True, text=True, env=env)
        assert result.returncode != 0
        assert "no pinned host key" in result.stderr


def _opts_env(host: str, pinned: Path, **extra: str):
    """Run ssh_host_key_opts with PROD_REMOTE_HOST set; return the completed process."""
    return subprocess.run(
        ["bash", "-c", '. "$1"; ssh_host_key_opts "$2"', "_", str(LIB), host],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "SSH_PINNED_KNOWN_HOSTS": str(pinned), "PROD_REMOTE_HOST": host, **extra},
    )


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="needs ssh-keygen")
def test_the_production_host_without_a_pinned_key_does_not_fall_back_to_accept_new(tmp_path: Path, pinned: Path):
    result = _opts_env("other-name.example.org", pinned)
    assert result.returncode == 1
    assert "accept-new" not in result.stdout
    assert "PROD_SSH_KNOWN_HOSTS" in result.stderr
    assert "PROD_SSH_ACCEPT_NEW_HOST_KEY" in result.stderr


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="needs ssh-keygen")
def test_accepting_a_new_production_key_needs_an_explicit_switch(tmp_path: Path, pinned: Path):
    result = _opts_env("other-name.example.org", pinned, PROD_SSH_ACCEPT_NEW_HOST_KEY="true")
    assert result.stdout.splitlines() == ["-o", "StrictHostKeyChecking=accept-new"]
    assert result.stderr == ""


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="needs ssh-keygen")
def test_the_ci_setup_stops_when_the_production_host_is_not_pinned(pinned: Path):
    result = subprocess.run(
        ["bash", "-c", '. "$1"; echo reached', "_", str(PROD_SSH_SETUP)],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "SSH_PRIVATE_KEY": "unused",
            "PROD_REMOTE_HOST": "unlisted.example.org",
            "SSH_PINNED_KNOWN_HOSTS": str(pinned),
        },
    )
    assert "reached" not in result.stdout
    assert result.returncode != 0
