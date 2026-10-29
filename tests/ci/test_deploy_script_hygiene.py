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
import contextlib
import gzip
import hashlib
import os
import shutil
import signal
import stat
import subprocess
import sys
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
# Records its argv; `events` is the one ordered log of what the deploy did.
printf '%s\n' "$*" >> "$FAKE_LOG/docker-argv"
case "$1" in
    compose) exit 1 ;;  # no compose plugin: fall through to docker-compose
    exec)
        case "$*" in
            *mariadb-admin*) printf '%s\n' "$*" >> "$FAKE_LOG/db-pings"; exit 0 ;;  # the database answers at once
            *"mariadbd --version"*) echo "mariadbd  Ver ${FAKE_SERVER_VERSION:-13.0.2}-MariaDB-ubu2604 for debian-linux-gnu"; exit 0 ;;
            *mariadb_upgrade_info*) printf '%s' "${FAKE_UPGRADE_INFO-13.0.2-MariaDB}"; exit 0 ;;
            *mariadb-dump*)
                echo dump >> "$FAKE_LOG/events"
                printf '%s' "${MYSQL_PWD-<unset>}" > "$FAKE_LOG/dump-pwd"
                [ "${FAKE_FAIL_DUMP:-0}" = 1 ] && exit 2
                # A dump queued behind a metadata lock: no output, no exit.
                [ "${FAKE_DUMP_STALL:-0}" = 1 ] && exec sleep 600
                # A slow but healthy dump: a burst of incompressible output every
                # second, for FAKE_DUMP_SLOW seconds in total.
                for _ in $(seq 1 "${FAKE_DUMP_SLOW:-0}"); do
                    printf -- '-- %s\n' "$(head -c 200000 /dev/urandom | base64 -w0)"
                    sleep 1
                done
                printf -- '-- MariaDB dump\nCREATE TABLE t (id INT);\n'
                [ "${FAKE_DUMP_NO_TRAILER:-0}" = 1 ] || printf -- '-- Dump completed on 2026-09-24\n'
                exit 0
                ;;
        esac
        echo migrate >> "$FAKE_LOG/events"
        n=$(ls "$FAKE_LOG" | grep -c '^exec-stdin' || true)
        cat > "$FAKE_LOG/exec-stdin.$n"
        printf '%s' "${MYSQL_PWD-<unset>}" > "$FAKE_LOG/exec-pwd.$n"
        # tools/apply_migrations.py's own statements: the ledger read, the
        # processlist on failure, the ledger write.
        if grep -q "SELECT 'ledger'" "$FAKE_LOG/exec-stdin.$n"; then
            printf 'kind\tfilename\tsha256\n'
            [ -f "$FAKE_LOG/ledger" ] && cat "$FAKE_LOG/ledger"
            exit 0
        fi
        if grep -q 'information_schema.PROCESSLIST' "$FAKE_LOG/exec-stdin.$n"; then
            printf 'kind\tID\n'
            printf 'proc\t42\troot\t18000\tQuery\tSending data\t\tSELECT COUNT(*) FROM tagger_processed_files t JOIN\n'
            exit 0
        fi
        grep -q '^INSERT INTO schema_migrations' "$FAKE_LOG/exec-stdin.$n" && exit 0
        [ "${FAKE_FAIL_MIGRATION:-0}" = 1 ] && exit 3
        if [ "${FAKE_LOCK_TIMEOUT:-0}" = 1 ]; then
            echo 'ERROR 1205 (HY000) at line 2: Lock wait timeout exceeded; try restarting transaction' >&2
            exit 1
        fi
        ;;
    buildx)
        # `docker buildx version` fails unless the test asks for buildx.
        [ "${FAKE_BUILDX:-0}" = 1 ] || exit 1
        [ "$2" = imagetools ] && echo "$6 -> $5" >> "$FAKE_LOG/promotions"
        ;;
    logs) echo '[Note] [Entrypoint]: Starting mariadb-upgrade' ;;
    # Containers the fake compose `run` left behind live as pid files in
    # $FAKE_LOG/containers/<name> (bug report 123).
    inspect)
        if [ "$2" = --type ]; then
            [ -e "$FAKE_LOG/containers/$4" ] && exit 0
            exit 1
        fi
        ;;
    rm)
        name="${@: -1}"
        echo "rm $name" >> "$FAKE_LOG/events"
        if [ -e "$FAKE_LOG/containers/$name" ] && [ "${FAKE_BACKUP_CONTAINER_STUCK:-0}" != 1 ]; then
            kill "$(cat "$FAKE_LOG/containers/$name")" 2>/dev/null
            rm -f "$FAKE_LOG/containers/$name"
        fi
        ;;
    ps)
        case "$*" in
            *com.docker.compose.service=db-backup*)
                ls "$FAKE_LOG/containers" 2>/dev/null
                [ "${FAKE_OTHER_BACKUP_RUNNING:-0}" = 1 ] && echo 0123456789ab
                ;;
        esac
        ;;
    push) echo "push $2" >> "$FAKE_LOG/pushes" ;;
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
printf 'compose IMAGE_TAG=%s %s\n' "${IMAGE_TAG-<unset>}" "$*" >> "$FAKE_LOG/events"
while [ $# -gt 0 ]; do
    case "$1" in
        --env-file)
            stat -c '%a' "$2" > "$FAKE_LOG/env-mode"
            stat -c '%a' "$(dirname "$2")" > "$FAKE_LOG/env-dir-mode"
            printf '%s' "$2" > "$FAKE_LOG/env-path"
            cp "$2" "$FAKE_LOG/env-content"
            shift 2 ;;
        -f) printf '%s' "$2" > "$FAKE_LOG/compose-path"; shift 2 ;;
        config) printf '%s\n' ${FAKE_SERVICES:-music-manager}; exit 0 ;;
        run)
            # FAKE_BACKUP_SERVICE_ORPHAN: what Watchtower did on 2026-09-27 -- the
            # run fails, but a copy of its container keeps dumping and writes
            # into the pre-deploy partial files beside it (bug report 123).
            if [ "${FAKE_BACKUP_SERVICE_ORPHAN:-0}" = 1 ]; then
                name="" prev=""
                for arg in "$@"; do [ "$prev" = --name ] && name="$arg"; prev="$arg"; done
                mkdir -p "$FAKE_LOG/containers"
                (
                    while :; do
                        for f in "$FAKE_BACKUP_DEST"/muma_db_pre-deploy_*.partial; do
                            [ -e "$f" ] && printf 'not gzip' >> "$f"
                        done
                        sleep 0.05
                    done
                ) </dev/null >/dev/null 2>&1 &
                echo "$!" > "$FAKE_LOG/containers/${name:-unnamed}"
                echo "orphan ${name:-unnamed}" >> "$FAKE_LOG/events"
                exit 1
            fi
            [ "${FAKE_FAIL_BACKUP_SERVICE:-0}" = 1 ] && exit "${FAKE_BACKUP_SERVICE_RC:-1}"; exit 0 ;;
        *) shift ;;
    esac
done
exit 0
"""

FAKE_DF = r"""#!/bin/bash
# `df -Pk PATH`: POSIX output, the free space from FAKE_DF_AVAIL_KB (default 50 GB).
printf '%s\n' "$*" >> "$FAKE_LOG/df-argv"
echo 'Filesystem     1024-blocks      Used Available Capacity Mounted on'
echo "/dev/sda1        103081248  52000000 ${FAKE_DF_AVAIL_KB:-52428800}      50% /"
"""

# The services docker/docker-compose.yml defines that matter to the deploy order.
STACK_SERVICES = "db phpmyadmin music-manager importer_worker soundcloud-fetcher genre-processor"


def _fake_bin(tmp_path: Path) -> tuple[Path, Path]:
    """Create fake ssh/docker/docker-compose binaries and the directory they log to."""
    bin_dir = tmp_path / "bin"
    log_dir = tmp_path / "log"
    bin_dir.mkdir()
    log_dir.mkdir()
    fakes = {"ssh": FAKE_SSH, "docker": FAKE_DOCKER, "docker-compose": FAKE_COMPOSE, "df": FAKE_DF}
    for name, body in fakes.items():
        target = bin_dir / name
        target.write_text(body, encoding="utf-8")
        target.chmod(0o755)
    return bin_dir, log_dir


def _env(tmp_path: Path, bin_dir: Path, log_dir: Path, **extra: str) -> dict[str, str]:
    """Environment for a script run: fake binaries first on PATH, HOME in the tmp dir."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        # The interpreter running these tests comes along: deploy.sh runs
        # tools/apply_migrations.py with python3, which in the CI image lives in
        # /usr/local/bin rather than /usr/bin.
        "PATH": f"{bin_dir}:{Path(sys.executable).parent}:/usr/bin:/bin",
        "HOME": str(home),
        "FAKE_LOG": str(log_dir),
        "REMOTE_HOST": "prod.invalid",
        "REMOTE_USER": "root",
        # No backup service installed: the deploy takes the docker-exec dump,
        # which the fake docker answers with a tiny but well-formed dump.
        "BACKUP_COMPOSE_DIR": str(tmp_path / "no-backup-service"),
        "PREDEPLOY_DUMP_MIN_BYTES": "10",
        "FAKE_SERVICES": STACK_SERVICES,
    }
    env.update(extra)
    return env


def _write_env_file(tmp_path: Path) -> Path:
    """Write a production-like env file whose root password needs careful parsing."""
    env_file = tmp_path / "prod.env"
    backups = tmp_path / "backups"
    backups.mkdir(exist_ok=True)
    env_file.write_text(
        f'MYSQL_ROOT_PASSWORD="{SECRET}"\nDB_DB=music-management\nDB_USER=muma\nDOCKER_USER=tester\nDB_PASS=unused#x\n'
        f"HOST_BACKUP_PATH={backups}\nCOMPOSE_PROFILES=soundcloud,youtube,telegram,importer\n",
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
    # exec 0 reads the (empty) ledger; then each file runs and is recorded.
    assert b"SELECT 'ledger'" in (log_dir / "exec-stdin.0").read_bytes()
    first = (log_dir / "exec-stdin.1").read_text(encoding="utf-8")
    assert first.startswith("SET SESSION lock_wait_timeout = 120; SET SESSION innodb_lock_wait_timeout = 120;\n")
    assert first.endswith(migrations[0].read_text(encoding="utf-8"))
    assert f"'{migrations[0].name}'" in (log_dir / "exec-stdin.2").read_text(encoding="utf-8")
    assert len(list(log_dir.glob("exec-stdin.*"))) == 1 + 2 * len(migrations)
    assert all(p.read_text() == SECRET for p in log_dir.glob("exec-pwd.*"))


def test_deploy_sh_fails_when_a_migration_fails(tmp_path: Path) -> None:
    bin_dir, log_dir = _fake_bin(tmp_path)
    env = _env(
        tmp_path,
        bin_dir,
        log_dir,
        FAKE_FAIL_MIGRATION="1",
        DEPLOY_TARGET_NAME="hygiene-test",
        LOCAL_COMPOSE_FILE="docker/docker-compose.yml",
        LOCAL_ENV_FILE=str(_write_env_file(tmp_path)),
    )
    result = subprocess.run(
        ["bash", str(DEPLOY_SH)], capture_output=True, text=True, env=env, cwd=tmp_path, check=False
    )
    assert result.returncode != 0
    assert "Remote deployment completed successfully" not in result.stdout
    assert "--remove-orphans" not in (log_dir / "compose-argv").read_text(), (
        "a failed migration must stop the deploy before up"
    )


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
    env = _env(
        tmp_path,
        bin_dir,
        log_dir,
        SSH_PRIVATE_KEY=str(key),
        PROD_REMOTE_HOST="prod.example.org",
        PROD_SSH_ACCEPT_NEW_HOST_KEY="true",
    )
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


# --- deploy order (bug report 050) ------------------------------------------
#
# The deploy used to recreate every container -- `db` included, with
# --force-recreate -- and migrate afterwards, with no backup, while
# release:build-images had already pushed :latest for Watchtower to find. The
# tests below run the real scripts against the fakes above and read the order
# of what happened out of $FAKE_LOG/events.


def _run_deploy(tmp_path: Path, **extra: str) -> tuple[subprocess.CompletedProcess, Path]:
    """Run scripts/deploy.sh against the fakes and return the result and log dir."""
    bin_dir, log_dir = _fake_bin(tmp_path)
    env = _env(
        tmp_path,
        bin_dir,
        log_dir,
        DEPLOY_TARGET_NAME="order-test",
        LOCAL_COMPOSE_FILE="docker/docker-compose.yml",
        LOCAL_ENV_FILE=str(_write_env_file(tmp_path)),
        **extra,
    )
    result = subprocess.run(
        ["bash", str(DEPLOY_SH)], capture_output=True, text=True, env=env, cwd=tmp_path, check=False
    )
    return result, log_dir


def _events(log_dir: Path) -> list[str]:
    """The ordered list of dumps, migrations and compose calls the deploy made."""
    path = log_dir / "events"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _index(events: list[str], predicate) -> int:
    """Position of the first event matching PREDICATE; fails the test if none does."""
    for position, event in enumerate(events):
        if predicate(event):
            return position
    pytest.fail(f"no matching event in {events}")


def _is_service_up(event: str) -> bool:
    """The final `up` of the application services (not the db prepare step)."""
    return event.startswith("compose") and " up " in event and "--remove-orphans" in event


def test_migrations_run_after_the_dump_and_before_any_container_is_recreated(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    events = _events(log_dir)

    dump = _index(events, lambda e: e == "dump")
    first_migration = _index(events, lambda e: e == "migrate")
    last_migration = len(events) - 1 - events[::-1].index("migrate")
    up = _index(events, _is_service_up)
    pull = _index(events, lambda e: e.startswith("compose") and " pull " in e + " ")
    assert dump < first_migration <= last_migration < pull < up, events

    backups = list((tmp_path / "backups").glob("muma_db_pre-deploy_*.sql.gz"))
    assert len(backups) == 1, "the verified dump must land in HOST_BACKUP_PATH"
    assert (log_dir / "dump-pwd").read_text() == SECRET
    assert SECRET not in (log_dir / "docker-argv").read_text(encoding="utf-8")


def test_the_database_is_ready_before_the_first_migration(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    docker_argv = (log_dir / "docker-argv").read_text(encoding="utf-8").splitlines()
    ping = next(i for i, line in enumerate(docker_argv) if "mariadb-admin --protocol=tcp -h 127.0.0.1 ping" in line)
    migration = next(i for i, line in enumerate(docker_argv) if line.startswith("exec") and " mariadb -u" in line)
    assert ping < migration


def test_no_container_is_force_recreated_and_db_is_left_alone_by_default(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    compose_argv = (log_dir / "compose-argv").read_text(encoding="utf-8")
    assert "--force-recreate" not in compose_argv

    db_up = [line for line in compose_argv.splitlines() if line.endswith(" up -d --no-deps --no-recreate db")]
    assert len(db_up) == 1, "db must only be started when missing, never recreated"

    service_up = next(line for line in compose_argv.splitlines() if "--remove-orphans" in line)
    services = service_up.split("--remove-orphans", 1)[1].split()
    assert "--no-deps" in service_up, "up <service> would otherwise converge db as a dependency"
    assert "db" not in services
    assert "soundcloud-fetcher" not in services and "genre-processor" not in services
    assert {"music-manager", "importer_worker", "phpmyadmin"} <= set(services)


def test_deploy_db_and_deploy_oneshots_opt_in(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path, DEPLOY_DB="1", DEPLOY_ONESHOTS="1")
    assert result.returncode == 0, result.stdout + result.stderr
    compose_argv = (log_dir / "compose-argv").read_text(encoding="utf-8").splitlines()
    assert [line for line in compose_argv if line.endswith(" up -d --no-deps db")], "DEPLOY_DB=1 must recreate db"
    service_up = next(line for line in compose_argv if "--remove-orphans" in line)
    services = service_up.split("--remove-orphans", 1)[1].split()
    assert {"soundcloud-fetcher", "genre-processor"} <= set(services)
    assert "db" not in services, "db is recreated in its own step, after the dump, never in the final up"


@pytest.mark.parametrize(
    ("knob", "reason"),
    [
        ({"FAKE_FAIL_DUMP": "1"}, "mariadb-dump exited"),
        ({"FAKE_DUMP_NO_TRAILER": "1"}, "no \"-- Dump completed\" trailer"),
        ({"PREDEPLOY_DUMP_MIN_BYTES": "100000"}, "below the"),
    ],
    ids=["dump-fails", "dump-truncated", "dump-too-small"],
)
def test_a_failed_dump_aborts_before_anything_is_migrated_or_recreated(
    tmp_path: Path, knob: dict[str, str], reason: str
) -> None:
    result, log_dir = _run_deploy(tmp_path, **knob)
    assert result.returncode != 0
    assert reason in result.stdout + result.stderr
    events = _events(log_dir)
    assert "migrate" not in events
    assert not any(_is_service_up(e) for e in events)
    assert not list((tmp_path / "backups").glob("*.sql.gz*")), "a failed dump must not leave a file behind"


def test_a_missing_backup_destination_aborts_the_deploy(tmp_path: Path) -> None:
    bin_dir, log_dir = _fake_bin(tmp_path)
    env_file = tmp_path / "prod.env"
    env_file.write_text(
        f'MYSQL_ROOT_PASSWORD="{SECRET}"\nDB_DB=music-management\nDOCKER_USER=tester\nHOST_BACKUP_PATH={tmp_path / "not-mounted"}\n'
        "COMPOSE_PROFILES=soundcloud,youtube,telegram,importer\n",
        encoding="utf-8",
    )
    env = _env(tmp_path, bin_dir, log_dir, DEPLOY_TARGET_NAME="order-test", LOCAL_ENV_FILE=str(env_file))
    result = subprocess.run(
        ["bash", str(DEPLOY_SH)], capture_output=True, text=True, env=env, cwd=tmp_path, check=False
    )
    assert result.returncode != 0
    assert "is the backup share mounted" in result.stdout
    assert "migrate" not in _events(log_dir)


def test_the_installed_backup_service_is_the_first_choice(tmp_path: Path) -> None:
    backup_dir = tmp_path / "muma-backup"
    backup_dir.mkdir()
    (backup_dir / "docker-compose.backup.yml").write_text("services: {}\n", encoding="utf-8")
    (backup_dir / ".env").write_text("DB_DB=x\n", encoding="utf-8")
    result, log_dir = _run_deploy(tmp_path, BACKUP_COMPOSE_DIR=str(backup_dir))
    assert result.returncode == 0, result.stdout + result.stderr
    events = _events(log_dir)
    backup = _index(events, lambda e: " run --rm -T --name order-test-predeploy-backup-" in e)
    run = events[backup]
    assert "-l com.centurylinklabs.watchtower.enable=false -e BACKUP_LABEL=pre-deploy db-backup" in run, run
    assert backup < _index(events, lambda e: e == "migrate")
    assert "dump" not in events, "the docker-exec fallback must not run when the service succeeded"


def test_a_failing_backup_service_falls_back_to_the_verified_dump(tmp_path: Path) -> None:
    backup_dir = tmp_path / "muma-backup"
    backup_dir.mkdir()
    (backup_dir / "docker-compose.backup.yml").write_text("services: {}\n", encoding="utf-8")
    (backup_dir / ".env").write_text("DB_DB=x\n", encoding="utf-8")
    result, log_dir = _run_deploy(tmp_path, BACKUP_COMPOSE_DIR=str(backup_dir), FAKE_FAIL_BACKUP_SERVICE="1")
    assert result.returncode == 0, result.stdout + result.stderr
    events = _events(log_dir)
    assert _index(events, lambda e: e == "dump") < _index(events, lambda e: e == "migrate")


def test_the_pre_up_hook_runs_between_the_migrations_and_up(tmp_path: Path) -> None:
    hook = tmp_path / "hook.sh"
    hook.write_text('#!/bin/bash\necho hook >> "$FAKE_LOG/events"\n', encoding="utf-8")
    hook.chmod(0o755)
    result, log_dir = _run_deploy(tmp_path, DEPLOY_PRE_UP_HOOK=str(hook))
    assert result.returncode == 0, result.stdout + result.stderr
    events = _events(log_dir)
    last_migration = len(events) - 1 - events[::-1].index("migrate")
    assert last_migration < _index(events, lambda e: e == "hook") < _index(events, _is_service_up)


def test_a_failing_pre_up_hook_stops_the_deploy_before_up(tmp_path: Path) -> None:
    hook = tmp_path / "hook.sh"
    hook.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    result, log_dir = _run_deploy(tmp_path, DEPLOY_PRE_UP_HOOK=str(hook))
    assert result.returncode != 0
    assert not any(_is_service_up(e) for e in _events(log_dir))


def test_image_tag_reaches_compose_and_is_validated(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path, IMAGE_TAG="0.71.3")
    assert result.returncode == 0, result.stdout + result.stderr
    up = next(e for e in _events(log_dir) if _is_service_up(e))
    assert "IMAGE_TAG=0.71.3 " in up

    (tmp_path / "bad").mkdir()
    bad, _ = _run_deploy(tmp_path / "bad", IMAGE_TAG="x'; rm -rf /; '")
    assert bad.returncode != 0
    assert "not a valid image tag" in bad.stdout


def test_ci_deploy_promotes_images_through_the_pre_up_hook() -> None:
    text = _text(CI_DEPLOY_SH)
    assert 'DEPLOY_PRE_UP_HOOK="$SCRIPT_DIR/ci/promote-release-images.sh"' in text
    assert "IMAGE_TAG" not in text.split("# 4. Deploy stack 1")[1].split("# 5.")[0].replace("(IMAGE_TAG unset)", ""), (
        "the stack must keep pulling :latest so muma:refresh-downloader still reaches it"
    )


# --- image tags: :latest only moves inside muma:deploy ----------------------

PROMOTE_SH = REPO_ROOT / "scripts" / "ci" / "promote-release-images.sh"
MUMA_IMAGE_ENV = (
    "DOCKER_USER=tester\nIMAGE_CORE=music-manager\nIMAGE_BASE=muma-base\nIMAGE_DOWNLOADER=muma-downloader\n"
    "IMAGE_TELEGRAM=muma-telegram\nIMAGE_IMPORTER=muma-importer\nIMAGE_TOOLS=muma-tools\n"
)
LMS_IMAGE_ENV = "IMAGE_NAME=tester/lms\nDOCKER_USER=someone-else\n"


def test_the_release_image_build_never_pushes_latest_or_stable(tmp_path: Path) -> None:
    bin_dir, log_dir = _fake_bin(tmp_path)
    env = _env(
        tmp_path,
        bin_dir,
        log_dir,
        PUSH_IMAGES="true",
        DOCKERHUB_USERNAME="tester",
        DOCKERHUB_TOKEN="tok",
        PROD_ENV_FILE=MUMA_IMAGE_ENV,
        PROD_ENV_FILE_LMS=LMS_IMAGE_ENV,
    )
    result = subprocess.run(["bash", str(BUILD_AND_PUSH_SH)], capture_output=True, text=True, env=env, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    pushes = (log_dir / "pushes").read_text(encoding="utf-8").splitlines()
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert pushes, "the release build must still push"
    assert not [p for p in pushes if p.endswith((":latest", ":stable"))], pushes
    for image in ["music-manager", "muma-base", "muma-downloader", "muma-telegram", "muma-importer", "muma-tools"]:
        assert f"push tester/{image}:{version}" in pushes
        assert f"push tester/{image}:rc" in pushes
    assert f"push tester/lms:{version}" in pushes, "lms needs the release version as promotion source"


@pytest.mark.parametrize("buildx", ["1", "0"], ids=["imagetools", "pull-tag-push"])
def test_promotion_moves_latest_and_stable_from_the_release_version(tmp_path: Path, buildx: str) -> None:
    bin_dir, log_dir = _fake_bin(tmp_path)
    muma_env = tmp_path / "muma.env"
    muma_env.write_text(MUMA_IMAGE_ENV, encoding="utf-8")
    lms_env = tmp_path / "lms.env"
    lms_env.write_text(LMS_IMAGE_ENV, encoding="utf-8")
    env = _env(
        tmp_path,
        bin_dir,
        log_dir,
        FAKE_BUILDX=buildx,
        DOCKERHUB_USERNAME="tester",
        DOCKERHUB_TOKEN="tok",
        PROMOTE_ENV_FILE=str(muma_env),
        PROMOTE_LMS_ENV_FILE=str(lms_env),
        VERSION="9.9.9-from-the-environment",
    )
    result = subprocess.run(["bash", str(PROMOTE_SH)], capture_output=True, text=True, env=env, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

    expected = [
        f"tester/{image}:{version} -> tester/{image}:latest"
        for image in ["muma-base", "muma-downloader", "muma-telegram", "muma-importer", "muma-tools", "music-manager"]
    ]
    expected += [f"tester/lms:{version} -> tester/lms:latest", f"tester/lms:{version} -> tester/lms:stable"]
    if buildx == "1":
        assert (log_dir / "promotions").read_text(encoding="utf-8").splitlines() == expected
    else:
        pushes = (log_dir / "pushes").read_text(encoding="utf-8").splitlines()
        assert pushes == ["push " + line.split(" -> ")[1] for line in expected]
    assert "tok" not in (log_dir / "docker-argv").read_text(encoding="utf-8")


def test_promotion_refuses_to_run_without_credentials(tmp_path: Path) -> None:
    bin_dir, log_dir = _fake_bin(tmp_path)
    env = _env(tmp_path, bin_dir, log_dir, DOCKERHUB_USERNAME="", DOCKERHUB_TOKEN="")
    result = subprocess.run(["bash", str(PROMOTE_SH)], capture_output=True, text=True, env=env, check=False)
    assert result.returncode != 0
    assert not (log_dir / "pushes").exists()


# --- post-deploy verification -----------------------------------------------

VERIFY_SH = REPO_ROOT / "scripts" / "ci" / "post-deploy-verify.sh"

FAKE_VERIFY_DOCKER = r"""#!/bin/bash
# Answers the two docker calls post-deploy-verify.sh makes. The first two
# `inspect` calls are the first sample (one per stack); later calls report
# FAKE_LATER_RESTARTS for music-manager.
case "$1" in
    ps) for arg; do case "$arg" in *project=*) echo "id-${arg##*project=}" ;; esac; done ;;
    inspect)
        project="${3%%|*}"
        n=$(( $(cat "$FAKE_LOG/inspect-count" 2>/dev/null || echo 0) + 1 ))
        echo "$n" > "$FAKE_LOG/inspect-count"
        restarts=2
        [ "$n" -gt 2 ] && restarts="${FAKE_LATER_RESTARTS:-2}"
        if [ "$project" = music-management ]; then
            echo "music-management|/music-manager|unless-stopped|running|${FAKE_HEALTH:-healthy}|$restarts"
            echo "music-management|/muma-soundcloud-fetcher|no|exited|none|0"
        else
            echo "lms|/lms|unless-stopped|running|healthy|0"
        fi
        ;;
esac
"""

FAKE_CURL = r"""#!/bin/bash
case "$*" in
    *ping.view*) printf '%s' "${FAKE_LMS_CODE:-400}" ;;
    *health*) printf '{"status":"ok","version":"%s"}' "${FAKE_VERSION:-1.2.3}" ;;
esac
"""


def _run_verify(tmp_path: Path, **extra: str) -> subprocess.CompletedProcess:
    """Run post-deploy-verify.sh against a fake production host."""
    bin_dir, log_dir = _fake_bin(tmp_path)
    for name, body in {"docker": FAKE_VERIFY_DOCKER, "curl": FAKE_CURL}.items():
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    env = _env(
        tmp_path,
        bin_dir,
        log_dir,
        VERIFY_SETTLE_SECONDS="0",
        VERIFY_POLL_SECONDS="0",
        VERIFY_TIMEOUT_SECONDS="2",
        **extra,
    )
    return subprocess.run(["bash", str(VERIFY_SH), "1.2.3"], capture_output=True, text=True, env=env, check=False)


def test_verify_passes_when_everything_stays_up(tmp_path: Path) -> None:
    result = _run_verify(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Post-deploy verification passed" in result.stdout


def test_verify_fails_when_a_container_restarts_between_samples(tmp_path: Path) -> None:
    """Both samples see "running"; only the restart count gives the crash loop away."""
    result = _run_verify(tmp_path, FAKE_LATER_RESTARTS="3")
    assert result.returncode != 0
    assert "music-manager restarted 1 time(s)" in result.stdout


def test_verify_fails_on_an_unhealthy_container(tmp_path: Path) -> None:
    result = _run_verify(tmp_path, FAKE_HEALTH="unhealthy")
    assert result.returncode != 0
    assert "healthcheck is failing" in result.stdout


def test_verify_fails_when_lms_does_not_answer(tmp_path: Path) -> None:
    result = _run_verify(tmp_path, FAKE_LMS_CODE="000")
    assert result.returncode != 0
    assert "Subsonic ping" in result.stdout


def test_verify_fails_on_the_wrong_version(tmp_path: Path) -> None:
    result = _run_verify(tmp_path, FAKE_VERSION="1.2.2")
    assert result.returncode != 0
    assert "not the 1.2.3 this pipeline deployed" in result.stdout


# --- migration ledger and lock timeout (bug report 068) -------------------------


def _ledger_line(path: Path, digest: str | None = None) -> str:
    """One row of the fake ledger, in the client's batch format."""
    return f"ledger\t{path.name}\t{digest or hashlib.sha256(path.read_bytes()).hexdigest()}\n"


def test_recorded_unchanged_migrations_are_skipped(tmp_path: Path) -> None:
    migrations = sorted(REPO_ROOT.glob("migrate_*.sql"))
    changed = migrations[-1]
    ledger = "".join(_ledger_line(p) for p in migrations[:-1]) + _ledger_line(changed, "0" * 64)
    bin_dir, log_dir = _fake_bin(tmp_path)
    (log_dir / "ledger").write_text(ledger, encoding="utf-8")
    env = _env(
        tmp_path,
        bin_dir,
        log_dir,
        DEPLOY_TARGET_NAME="ledger-test",
        LOCAL_COMPOSE_FILE="docker/docker-compose.yml",
        LOCAL_ENV_FILE=str(_write_env_file(tmp_path)),
    )
    result = subprocess.run(
        ["bash", str(DEPLOY_SH)], capture_output=True, text=True, env=env, cwd=tmp_path, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # The ledger read, then only the file whose hash differs: run and record.
    stdins = sorted(log_dir.glob("exec-stdin.*"), key=lambda p: int(p.suffix[1:]))
    assert len(stdins) == 3, [p.read_text()[:80] for p in stdins]
    assert stdins[1].read_text(encoding="utf-8").endswith(changed.read_text(encoding="utf-8"))
    assert f"{len(migrations) - 1} migration(s) recorded" in result.stdout
    assert f"{changed.name} (changed)" in result.stdout


def test_a_migration_blocked_on_a_lock_stops_the_deploy_before_up(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path, FAKE_LOCK_TIMEOUT="1", MIGRATION_LOCK_WAIT_SECONDS="7")
    assert result.returncode != 0
    output = result.stdout + result.stderr
    first = sorted(REPO_ROOT.glob("migrate_*.sql"))[0].name
    assert f"{first} waited more than 7s for a lock" in output
    # The client's line number counts the one-line prelude; the report counts the file's.
    assert "at line 1:" in output
    assert "Sessions on the database server" in output
    assert "SELECT COUNT(*) FROM tagger_processed_files" in output
    assert "7; SET SESSION innodb_lock_wait_timeout = 7;" in (log_dir / "exec-stdin.1").read_text()
    assert not any(_is_service_up(e) for e in _events(log_dir))
    assert SECRET not in output


def test_a_stalled_fallback_dump_is_stopped_and_refuses_the_deploy(tmp_path: Path) -> None:
    started = time.monotonic()
    result, log_dir = _run_deploy(tmp_path, FAKE_DUMP_STALL="1", PREDEPLOY_DUMP_STALL_SECONDS="2")
    assert result.returncode != 0
    # The fake dump sleeps 600 s. Anything well under that proves the watchdog stopped it; the
    # margin is wide because the rest of deploy.sh takes tens of seconds on a loaded runner
    # (a 45 s bound against a 60 s sleep failed backend:unit on 2026-09-27).
    assert time.monotonic() - started < 300, "the watchdog must not wait for the stalled dump"
    assert "wrote nothing for 2 s" in result.stdout + result.stderr
    events = _events(log_dir)
    assert "migrate" not in events
    assert not any(_is_service_up(e) for e in events)
    assert not list((tmp_path / "backups").glob("*.sql.gz*")), "a stalled dump must not leave a file behind"


def test_a_stalled_backup_service_does_not_fall_back(tmp_path: Path) -> None:
    """Exit 3 is tools/db_backup.py's stall watchdog: a second dump would queue behind the same lock."""
    backup_dir = tmp_path / "backup-service"
    backup_dir.mkdir()
    (backup_dir / "docker-compose.backup.yml").write_text("services: {}\n", encoding="utf-8")
    (backup_dir / ".env").write_text("X=1\n", encoding="utf-8")
    result, log_dir = _run_deploy(
        tmp_path, BACKUP_COMPOSE_DIR=str(backup_dir), FAKE_FAIL_BACKUP_SERVICE="1", FAKE_BACKUP_SERVICE_RC="3"
    )
    assert result.returncode != 0
    assert "pre-deploy dump stalled" in result.stdout + result.stderr
    events = _events(log_dir)
    assert "dump" not in events
    assert "migrate" not in events


# --- one dump writer at a time (bug report 123) ------------------------------
#
# On 2026-09-27 Watchtower's hourly session recreated the running db-backup
# container while the deploy was dumping: compose reported the run as failed,
# the fallback dump started, and the recreated container's second
# tools/db_backup.py wrote into the same file. gzip -t refused the result.


def _backup_service_dir(tmp_path: Path) -> Path:
    """An installed backup compose file, so the deploy tries the db-backup service first."""
    backup_dir = tmp_path / "muma-backup"
    backup_dir.mkdir()
    (backup_dir / "docker-compose.backup.yml").write_text("services: {}\n", encoding="utf-8")
    (backup_dir / ".env").write_text("DB_DB=x\n", encoding="utf-8")
    return backup_dir


def _kill_leftover_containers(log_dir: Path) -> None:
    """Stop the fake containers a test left running, so no writer outlives it."""
    for pid_file in (log_dir / "containers").glob("*") if (log_dir / "containers").is_dir() else []:
        with contextlib.suppress(ProcessLookupError, ValueError):
            os.kill(int(pid_file.read_text().strip()), signal.SIGTERM)


def test_a_failed_backup_run_is_gone_before_the_fallback_dump_starts(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    backups.mkdir(exist_ok=True)
    result, log_dir = _run_deploy(
        tmp_path,
        BACKUP_COMPOSE_DIR=str(_backup_service_dir(tmp_path)),
        FAKE_BACKUP_SERVICE_ORPHAN="1",
        FAKE_BACKUP_DEST=str(backups),
    )
    _kill_leftover_containers(log_dir)
    assert result.returncode == 0, result.stdout + result.stderr
    events = _events(log_dir)
    orphan = _index(events, lambda e: e.startswith("orphan order-test-predeploy-backup-"))
    name = events[orphan].split(" ", 1)[1]
    removed = _index(events, lambda e: e == f"rm {name}")
    assert orphan < removed < _index(events, lambda e: e == "dump") < _index(events, lambda e: e == "migrate")
    assert not (log_dir / "containers" / name).exists()
    finished = list(backups.glob("muma_db_pre-deploy_*_fallback.sql.gz"))
    assert len(finished) == 1, list(backups.iterdir())
    with gzip.open(finished[0], "rt", encoding="utf-8") as dump:
        assert "-- Dump completed" in dump.read(), "a second writer corrupted the dump"


def test_a_backup_container_that_will_not_go_refuses_the_deploy(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    backups.mkdir(exist_ok=True)
    result, log_dir = _run_deploy(
        tmp_path,
        BACKUP_COMPOSE_DIR=str(_backup_service_dir(tmp_path)),
        FAKE_BACKUP_SERVICE_ORPHAN="1",
        FAKE_BACKUP_CONTAINER_STUCK="1",
        FAKE_BACKUP_DEST=str(backups),
        PREDEPLOY_BACKUP_RM_WAIT_SECONDS="2",
    )
    _kill_leftover_containers(log_dir)
    assert result.returncode != 0
    assert "would be a second writer" in result.stdout
    events = _events(log_dir)
    assert "dump" not in events, "the fallback must never start beside a live backup container"
    assert "migrate" not in events
    assert not any(_is_service_up(e) for e in events)


def test_another_running_backup_container_refuses_the_fallback(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path, FAKE_OTHER_BACKUP_RUNNING="1")
    assert result.returncode != 0
    assert "another db-backup container is still running" in result.stdout
    events = _events(log_dir)
    assert "dump" not in events
    assert "migrate" not in events


def test_the_fallback_dump_writes_under_names_of_its_own(tmp_path: Path) -> None:
    """A db-backup dump taken in the same second can never share the fallback's file."""
    text = _text(DEPLOY_SH)
    assert 'FILE=\\"\\$DEST/muma_db_pre-deploy_\\${STAMP}_fallback.sql.gz\\"' in text
    assert 'PART=\\"\\$DEST/muma_db_pre-deploy_\\${STAMP}_fallback.\\$\\$.sql.gz.partial\\"' in text
    result, _ = _run_deploy(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [p.name for p in (tmp_path / "backups").iterdir()][0].endswith("_fallback.sql.gz")


def test_a_slow_but_growing_fallback_dump_is_not_stopped(tmp_path: Path) -> None:
    """The watchdog measures file growth: a dump that keeps writing is never a stall."""
    result, log_dir = _run_deploy(tmp_path, FAKE_DUMP_SLOW="5", PREDEPLOY_DUMP_STALL_SECONDS="3")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "wrote nothing" not in result.stdout
    assert _index(_events(log_dir), lambda e: e == "dump") < _index(_events(log_dir), lambda e: e == "migrate")


def test_deploy_has_no_default_registry_user() -> None:
    """The remote compose file is found by `<DOCKER_USER>/muma`; a guessed user matches the wrong stack."""
    text = DEPLOY_SH.read_text(encoding="utf-8")
    assert "DOCKER_USER:-muma" not in text
    assert "Error: DOCKER_USER is not set" in text
