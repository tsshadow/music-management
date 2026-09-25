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
PINNED = ROOT / "scripts" / "ssh" / "known_hosts"
PROD_SSH_SETUP = ROOT / "scripts" / "ci" / "prod-ssh-setup.sh"
SSH_SCRIPTS = [
    ROOT / "scripts" / "deploy.sh",
    ROOT / "scripts" / "ci-deploy.sh",
    PROD_SSH_SETUP,
    ROOT / "scripts" / "ci" / "post-deploy-verify.sh",
    ROOT / "scripts" / "ci" / "verify-prod-version.sh",
    ROOT / "services" / "music-management-server" / "scripts" / "deploy-stack.sh",
]


def _code_lines(path: Path) -> list[str]:
    """The lines of a shell script that are not comments."""
    return [line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")]


def _opts(host: str, pinned: Path = PINNED) -> list[str]:
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


def test_the_default_production_host_is_pinned():
    default = re.search(r'PROD_REMOTE_HOST:-([^}"]+)', PROD_SSH_SETUP.read_text(encoding="utf-8"))
    assert default, "prod-ssh-setup.sh no longer has a default host"
    hosts = {line.split()[0] for line in PINNED.read_text(encoding="utf-8").splitlines() if line and line[0] != "#"}
    assert default.group(1) in hosts


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="needs ssh-keygen")
def test_a_pinned_host_is_checked_strictly_against_the_pinned_file_only():
    assert _opts("192.0.2.27") == [
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={PINNED}",
    ]


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="needs ssh-keygen")
def test_an_unpinned_host_learns_once_and_refuses_a_changed_key():
    assert _opts("portainer.example.invalid") == ["-o", "StrictHostKeyChecking=accept-new"]


def test_a_missing_pinned_file_never_means_accept_anything(tmp_path: Path):
    assert _opts("192.0.2.27", tmp_path / "absent") == ["-o", "StrictHostKeyChecking=accept-new"]


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="needs ssh-keygen")
def test_the_pinned_file_parses_as_known_hosts():
    """A typo in a key line would make ssh-keygen skip it, and then no key would match."""
    result = subprocess.run(["ssh-keygen", "-lf", str(PINNED)], capture_output=True, text=True, check=True)
    assert len(result.stdout.splitlines()) >= 1
