"""Secret hygiene of the deploy and image-publishing scripts.

Bug report 038: the deploy put the whole production .env, base64-encoded, on the
ssh command line, and the MariaDB root password on the `mariadb -p` command line
-- both readable through `ps` on the runner and on the production host. It left
the env file world-readable in /tmp, preferred a compose binary from /tmp while
running as root, left the Docker Hub token and the prod-key ssh-agent behind on
the shared runner, and wrote prod .env files into the docker build context.

Two kinds of test live here. The static ones grep the scripts for the shapes
that caused each defect, so a copy-paste from an old script cannot quietly bring
one back. The behavioural ones run the real scripts against fake `ssh`,
`docker` and `docker-compose` binaries that execute the "remote" half locally
and record what they were given -- the only way to prove the remote script
actually receives the env file, gives it mode 0600, and deletes it again.
"""

from __future__ import annotations

import base64
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = REPO_ROOT / "scripts" / "deploy.sh"
DEPLOY_STACK_SH = REPO_ROOT / "services" / "music-management-server" / "scripts" / "deploy-stack.sh"
CI_DEPLOY_SH = REPO_ROOT / "scripts" / "ci-deploy.sh"
PROD_SSH_SETUP_SH = REPO_ROOT / "scripts" / "ci" / "prod-ssh-setup.sh"
DOCKER_HUB_SESSION_SH = REPO_ROOT / "scripts" / "ci" / "docker-hub-session.sh"
BUILD_AND_PUSH_SH = REPO_ROOT / "scripts" / "ci" / "build-and-push-images.sh"
REFRESH_SH = REPO_ROOT / "scripts" / "ci" / "refresh-downloader-image.sh"
DOTENV_SH = REPO_ROOT / "scripts" / "lib" / "dotenv.sh"

DEPLOY_SCRIPTS = [DEPLOY_SH, DEPLOY_STACK_SH]
IMAGE_SCRIPTS = [BUILD_AND_PUSH_SH, REFRESH_SH]

SECRET = "s3cr#t'pass word"


def _text(path: Path) -> str:
    """Read a script as UTF-8 text."""
    return path.read_text(encoding="utf-8")


# --- static checks ------------------------------------------------------------


@pytest.mark.parametrize("script", DEPLOY_SCRIPTS, ids=lambda p: p.name)
def test_the_env_file_is_never_base64_encoded_onto_a_command_line(script: Path) -> None:
    text = _text(script)
    assert "BASE64_ENV" not in text
    assert "B64_ENV" not in text
    for line in text.splitlines():
        if "base64" in line:
            assert "ENV_FILE" not in line and "ENV_PATH" not in line, line


@pytest.mark.parametrize("script", DEPLOY_SCRIPTS, ids=lambda p: p.name)
def test_the_env_file_is_not_written_to_tmp(script: Path) -> None:
    assert "/tmp/.env" not in _text(script)


@pytest.mark.parametrize("script", DEPLOY_SCRIPTS, ids=lambda p: p.name)
def test_no_compose_binary_is_taken_from_tmp(script: Path) -> None:
    assert "/tmp/docker-compose-v2" not in _text(script)


@pytest.mark.parametrize("script", DEPLOY_SCRIPTS, ids=lambda p: p.name)
def test_no_password_goes_on_an_argv(script: Path) -> None:
    text = _text(script)
    assert '-p\\"$' not in text, "mariadb -p\"$PASS\" puts the password in ps"
    assert '-p"$' not in text, "mariadb -p\"$PASS\" puts the password in ps"
    assert "--password=" not in text
    assert "sshpass -p" not in text, "sshpass -p puts the ssh password in ps; use SSHPASS + -e"


@pytest.mark.parametrize("script", DEPLOY_SCRIPTS, ids=lambda p: p.name)
def test_the_remote_env_file_is_private_and_removed(script: Path) -> None:
    text = _text(script)
    assert "umask 077" in text
    assert ".muma-deploy" in text
    assert "trap 'rm -rf" in text


def test_the_migration_password_travels_through_the_environment() -> None:
    text = _text(DEPLOY_SH)
    assert "docker exec -i -e MYSQL_PWD music-management-db-1" in text
    assert "read -r MYSQL_PWD" in text


def test_docker_login_happens_only_inside_a_throwaway_docker_config() -> None:
    offenders = []
    for path in sorted(REPO_ROOT.rglob("*.sh")):
        if "node_modules" in path.parts or ".git" in path.parts or path == DOCKER_HUB_SESSION_SH:
            continue
        for line in _text(path).splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("echo"):
                continue
            if "docker login" in stripped:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {stripped}")
    assert not offenders, "log in through docker_hub_login (scripts/ci/docker-hub-session.sh)"


@pytest.mark.parametrize("script", IMAGE_SCRIPTS, ids=lambda p: p.name)
def test_image_scripts_log_out_and_keep_prod_env_out_of_the_checkout(script: Path) -> None:
    text = _text(script)
    assert "docker_hub_login" in text
    assert "docker_hub_logout" in text
    assert "trap cleanup_on_exit EXIT" in text
    assert '"$PROJECT_ROOT/.env"' not in text.split("PUSH_IMAGES=false: building")[0], (
        "the prod .env must not be written into the checkout (the build context)"
    )


def test_ci_deploy_keeps_prod_env_out_of_the_checkout() -> None:
    text = _text(CI_DEPLOY_SH)
    assert '"$PROJECT_ROOT/.env"' not in text
    assert "services/music-management-server/.env" not in text
    assert "trap cleanup_deploy EXIT" in text


def test_env_files_are_excluded_from_every_build_context() -> None:
    for ignore in [REPO_ROOT / ".dockerignore", REPO_ROOT / "services" / "music-management-server" / ".dockerignore"]:
        entries = {line.strip() for line in _text(ignore).splitlines()}
        assert ".env" in entries, ignore
        assert "**/.env" in entries, ignore


def test_no_dockerfile_copies_an_env_file() -> None:
    """The .dockerignore entries above would silently break one that did."""
    for path in list(REPO_ROOT.glob("docker/Dockerfile*")) + list(
        (REPO_ROOT / "services" / "music-management-server").glob("Dockerfile*")
    ):
        for line in _text(path).splitlines():
            if line.strip().upper().startswith(("COPY", "ADD")):
                assert ".env" not in line, f"{path.name}: {line}"


def test_prod_ssh_setup_kills_its_agent() -> None:
    text = _text(PROD_SSH_SETUP_SH)
    assert "trap prod_ssh_teardown EXIT" in text
    assert "ssh-add -t" in text


# --- the .env parser ----------------------------------------------------------


def _parse(line: str) -> str:
    """Run dotenv_parse_line on LINE in bash and return what it printed."""
    result = subprocess.run(
        ["bash", "-c", '. "$1"; dotenv_parse_line "$2"', "_", str(DOTENV_SH), line],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.rstrip("\n")


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("MYSQL_ROOT_PASSWORD=ab#cd", "MYSQL_ROOT_PASSWORD=ab#cd"),
        ("PASS=#leading", "PASS=#leading"),
        ("PASS=value # a comment", "PASS=value"),
        ("PASS=value\t# a comment", "PASS=value"),
        ("PASS='quoted # kept'", "PASS=quoted # kept"),
        ('PASS="double # kept" # comment', "PASS=double # kept"),
        ("  PASS = spaced  ", "PASS=spaced"),
        ("export PASS=exported", "PASS=exported"),
        ("PASS=a=b=c", "PASS=a=b=c"),
        ("EMPTY=", "EMPTY="),
        ("PASS=crlf\r", "PASS=crlf"),
        ("# PASS=commented", ""),
        ("   # indented comment", ""),
        ("", ""),
        ("not an assignment", ""),
        ("1BAD=key", ""),
    ],
)
def test_dotenv_parse_line(line: str, expected: str) -> None:
    assert _parse(line) == expected


def test_dotenv_load_exports_and_keep_existing_respects_the_environment(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=from#file\nB=from-file # comment\n", encoding="utf-8")
    script = '. "$1"; dotenv_load "$2" "$3"; printf "%s|%s" "$A" "$B"'
    plain = subprocess.run(
        ["bash", "-c", script, "_", str(DOTENV_SH), str(env_file), ""],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "B": "from-env"},
    )
    assert plain.stdout == "from#file|from-file"
    keep = subprocess.run(
        ["bash", "-c", script, "_", str(DOTENV_SH), str(env_file), "--keep-existing"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "B": "from-env"},
    )
    assert keep.stdout == "from#file|from-env"


# --- behavioural: the real scripts against fake ssh/docker --------------------

FAKE_SSH = r"""#!/bin/bash
# Records its argv, then runs the remote command locally with stdin passed on.
printf '%s\n' "$*" >> "$FAKE_LOG/ssh-argv"
while [ $# -gt 0 ]; do
    case "$1" in
        -o|-i|-p) shift 2 ;;
        -*) shift ;;
        *) break ;;
    esac
done
shift  # user@host
exec bash -c "$1"
"""

FAKE_DOCKER = r"""#!/bin/bash
printf '%s\n' "$*" >> "$FAKE_LOG/docker-argv"
case "$1" in
    compose) exit 1 ;;  # no compose plugin: fall through to docker-compose
    exec)
        n=$(ls "$FAKE_LOG" | grep -c '^exec-stdin' || true)
        cat > "$FAKE_LOG/exec-stdin.$n"
        printf '%s' "${MYSQL_PWD-<unset>}" > "$FAKE_LOG/exec-pwd.$n"
        ;;
    login)
        cat > "$FAKE_LOG/login-stdin"
        printf '%s' "$DOCKER_CONFIG" > "$FAKE_LOG/login-config-dir"
        mkdir -p "$DOCKER_CONFIG" && echo '{"auths":{"x":{}}}' > "$DOCKER_CONFIG/config.json"
        ;;
esac
exit 0
"""

FAKE_COMPOSE = r"""#!/bin/bash
printf '%s\n' "$*" >> "$FAKE_LOG/compose-argv"
while [ $# -gt 0 ]; do
    case "$1" in
        --env-file)
            stat -c '%a' "$2" > "$FAKE_LOG/env-mode"
            stat -c '%a' "$(dirname "$2")" > "$FAKE_LOG/env-dir-mode"
            printf '%s' "$2" > "$FAKE_LOG/env-path"
            cp "$2" "$FAKE_LOG/env-content"
            shift 2 ;;
        -f) printf '%s' "$2" > "$FAKE_LOG/compose-path"; shift 2 ;;
        config) echo music-manager; exit 0 ;;
        *) shift ;;
    esac
done
exit 0
"""


def _fake_bin(tmp_path: Path) -> tuple[Path, Path]:
    """Create fake ssh/docker/docker-compose binaries and the directory they log to."""
    bin_dir = tmp_path / "bin"
    log_dir = tmp_path / "log"
    bin_dir.mkdir()
    log_dir.mkdir()
    for name, body in {"ssh": FAKE_SSH, "docker": FAKE_DOCKER, "docker-compose": FAKE_COMPOSE}.items():
        target = bin_dir / name
        target.write_text(body, encoding="utf-8")
        target.chmod(0o755)
    return bin_dir, log_dir


def _env(tmp_path: Path, bin_dir: Path, log_dir: Path, **extra: str) -> dict[str, str]:
    """Environment for a script run: fake binaries first on PATH, HOME in the tmp dir."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(home),
        "FAKE_LOG": str(log_dir),
        "REMOTE_HOST": "prod.invalid",
        "REMOTE_USER": "root",
    }
    env.update(extra)
    return env


def _write_env_file(tmp_path: Path) -> Path:
    """Write a production-like env file whose root password needs careful parsing."""
    env_file = tmp_path / "prod.env"
    env_file.write_text(
        f'MYSQL_ROOT_PASSWORD="{SECRET}"\nDB_DB=music-management\nDB_USER=muma\nDB_PASS=unused#x\n',
        encoding="utf-8",
    )
    return env_file


def _assert_remote_env_handling(tmp_path: Path, log_dir: Path, env_file: Path, stack: str) -> None:
    """Assert the env file reached compose privately, left no trace, and never hit an argv."""
    deploy_dir = tmp_path / "home" / ".muma-deploy" / stack
    argv = (log_dir / "ssh-argv").read_text(encoding="utf-8")
    encoded = base64.b64encode(env_file.read_bytes()).decode()
    assert SECRET not in argv
    assert encoded[:40] not in argv

    assert (log_dir / "env-content").read_bytes() == env_file.read_bytes()
    assert (log_dir / "env-mode").read_text().strip() == "600"
    assert (log_dir / "env-dir-mode").read_text().strip() == "700"
    env_path = Path((log_dir / "env-path").read_text())
    assert env_path.parent.parent == deploy_dir
    assert not env_path.exists(), "the env file must be gone once the deploy ends"
    assert not list(deploy_dir.glob("run.*"))

    assert Path((log_dir / "compose-path").read_text()) == deploy_dir / "docker-compose.yml"
    assert (deploy_dir / "docker-compose.yml").is_file()
    assert stat.S_IMODE(deploy_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(deploy_dir.parent.stat().st_mode) == 0o700


def test_deploy_sh_streams_env_and_password_over_stdin(tmp_path: Path) -> None:
    bin_dir, log_dir = _fake_bin(tmp_path)
    env_file = _write_env_file(tmp_path)
    env = _env(
        tmp_path,
        bin_dir,
        log_dir,
        DEPLOY_TARGET_NAME="hygiene-test",
        LOCAL_COMPOSE_FILE="docker/docker-compose.yml",
        LOCAL_ENV_FILE=str(env_file),
    )
    result = subprocess.run(
        ["bash", str(DEPLOY_SH)], capture_output=True, text=True, env=env, cwd=tmp_path, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr

    _assert_remote_env_handling(tmp_path, log_dir, env_file, "hygiene-test")

    migrations = sorted(REPO_ROOT.glob("migrate_*.sql"))
    assert migrations, "expected migrate_*.sql files in the repository root"
    docker_argv = (log_dir / "docker-argv").read_text(encoding="utf-8")
    assert SECRET not in docker_argv
    assert (log_dir / "exec-pwd.0").read_text() == SECRET
    assert (log_dir / "exec-stdin.0").read_bytes() == migrations[0].read_bytes()
    assert len(list(log_dir.glob("exec-stdin.*"))) == len(migrations)


def test_deploy_sh_fails_when_a_migration_fails(tmp_path: Path) -> None:
    bin_dir, log_dir = _fake_bin(tmp_path)
    failing = bin_dir / "docker"
    failing.write_text(
        FAKE_DOCKER.replace("    exec)\n", "    exec)\n        cat >/dev/null; exit 3\n"), encoding="utf-8"
    )
    env = _env(
        tmp_path,
        bin_dir,
        log_dir,
        DEPLOY_TARGET_NAME="hygiene-test",
        LOCAL_COMPOSE_FILE="docker/docker-compose.yml",
        LOCAL_ENV_FILE=str(_write_env_file(tmp_path)),
    )
    result = subprocess.run(
        ["bash", str(DEPLOY_SH)], capture_output=True, text=True, env=env, cwd=tmp_path, check=False
    )
    assert result.returncode != 0
    assert "Remote deployment completed successfully" not in result.stdout


def test_deploy_stack_sh_streams_env_over_stdin(tmp_path: Path) -> None:
    bin_dir, log_dir = _fake_bin(tmp_path)
    env_file = _write_env_file(tmp_path)
    env = _env(
        tmp_path,
        bin_dir,
        log_dir,
        DEPLOY_TARGET_NAME="lms-hygiene",
        LOCAL_COMPOSE_FILE=str(REPO_ROOT / "services" / "music-management-server" / "docker-compose.yml"),
        LOCAL_ENV_FILE=str(env_file),
    )
    result = subprocess.run(
        ["bash", str(DEPLOY_STACK_SH)], capture_output=True, text=True, env=env, cwd=tmp_path, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_remote_env_handling(tmp_path, log_dir, env_file, "lms-hygiene")


def test_docker_hub_session_logs_in_privately_and_cleans_up(tmp_path: Path) -> None:
    bin_dir, log_dir = _fake_bin(tmp_path)
    real_config = tmp_path / "home" / ".docker"
    (real_config / "cli-plugins").mkdir(parents=True)
    env = _env(tmp_path, bin_dir, log_dir, DOCKERHUB_USERNAME="tester", DOCKERHUB_TOKEN="tok-123")
    script = '. "$1"; trap docker_hub_logout EXIT; docker_hub_login; test -L "$DOCKER_CONFIG/cli-plugins"'
    result = subprocess.run(
        ["bash", "-c", script, "_", str(DOCKER_HUB_SESSION_SH)], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (log_dir / "login-stdin").read_text().strip() == "tok-123"
    assert "tok-123" not in (log_dir / "docker-argv").read_text()
    session_dir = Path((log_dir / "login-config-dir").read_text())
    assert session_dir != real_config
    assert not session_dir.exists(), "the session DOCKER_CONFIG must be removed on exit"
    assert (real_config / "cli-plugins").is_dir(), "the plugin symlink target must survive the cleanup"
    assert not (real_config / "config.json").exists()


@pytest.mark.skipif(
    not (shutil.which("ssh-agent") and shutil.which("ssh-keygen") and shutil.which("ssh-add")),
    reason="needs OpenSSH client tools",
)
def test_prod_ssh_setup_agent_dies_with_the_sourcing_shell(tmp_path: Path) -> None:
    bin_dir, log_dir = _fake_bin(tmp_path)
    keyscan = bin_dir / "ssh-keyscan"
    keyscan.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    keyscan.chmod(0o755)
    key = tmp_path / "id_test"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    env = _env(tmp_path, bin_dir, log_dir, SSH_PRIVATE_KEY=str(key))
    env["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    pid_file = tmp_path / "agent.pid"
    script = 'set -e; . "$1"; echo "$SSH_AGENT_PID" > "$2"; ssh-add -l >/dev/null'
    result = subprocess.run(
        ["bash", "-c", script, "_", str(PROD_SSH_SETUP_SH), str(pid_file)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    pid = int(pid_file.read_text().strip())
    # SIGTERM is asynchronous; give the agent a moment to act on it.
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail(f"ssh-agent {pid} outlived the shell that sourced prod-ssh-setup.sh")
