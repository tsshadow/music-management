"""The production host key is pinned, never accepted blindly.

Every deploy and verify script used to connect with StrictHostKeyChecking=no
after appending whatever ssh-keyscan returned to the runner's known_hosts, so
anything answering on the production address got the root key's signature,
the production env file on stdin and the migrations
(docs/bug-reports/081-compose-logs-grow-without-bound.md).
"""

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


def test_the_ci_variable_is_the_pinned_file_when_no_override_is_set(pinned: Path):
    result = subprocess.run(
        ["bash", "-c", '. "$1"; printf %s "$SSH_PINNED_KNOWN_HOSTS"', "_", str(LIB)],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": "/usr/bin:/bin", "PROD_SSH_KNOWN_HOSTS": str(pinned)},
    )
    assert result.stdout == str(pinned)


def test_the_ci_setup_stops_when_the_pinned_file_is_missing():
    code = "\n".join(_code_lines(PROD_SSH_SETUP))
    assert "PROD_SSH_KNOWN_HOSTS" in PROD_SSH_SETUP.read_text(encoding="utf-8")
    assert '[ ! -f "$SSH_PINNED_KNOWN_HOSTS" ]' in code


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
