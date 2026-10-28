"""The deploy's disk pre-check, the image prune after it, and the order around `db`.

Bug report 094. On 2026-09-26 production's root disk was 95% full: every deploy
pulled a new set of images and nothing ever removed the old ones. A pull into a
full disk half-deploys, so the deploy now refuses to start below a free-space
floor, and a verified deploy prunes what no container and no rollback needs.

The same review found that DEPLOY_DB=1 recreated `db` before the pre-deploy
dump ran, and that the next DEPLOY_DB=1 is a 12.3 -> 13.0 major upgrade with
nothing set to run mariadb-upgrade. These tests run the real scripts against the
fake ssh/docker/compose/df binaries of test_deploy_script_hygiene.py.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

from tests.ci.test_deploy_script_hygiene import (
    CI_DEPLOY_SH,
    REPO_ROOT,
    _env,
    _events,
    _fake_bin,
    _index,
    _is_service_up,
    _run_deploy,
)

PRUNE_SH = REPO_ROOT / "scripts" / "ci" / "prune-prod-images.sh"
PROD_COMPOSE = REPO_ROOT / "docker" / "docker-compose.yml"
DIGEST_PIN = re.compile(r"^mariadb:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$")


# --- disk pre-check -----------------------------------------------------------


def test_a_nearly_full_disk_stops_the_deploy_before_anything_happens(tmp_path: Path) -> None:
    # 5.5 GB free: the incident's number.
    result, log_dir = _run_deploy(tmp_path, FAKE_DF_AVAIL_KB=str(int(5.5 * 1024 * 1024)))
    assert result.returncode != 0
    assert "only 5.5 GB free on /, below the 8 GB this deploy needs" in result.stdout
    assert "prune-prod-images.sh" in result.stdout
    events = _events(log_dir)
    assert "dump" not in events and "migrate" not in events
    assert not any(" pull " in e + " " or " up " in e for e in events if e.startswith("compose")), events


def test_enough_space_passes_and_is_logged(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Disk: 50.0 GB free on / (minimum 8 GB)." in result.stdout
    assert (log_dir / "df-argv").read_text().split() == ["-Pk", "/"]


def test_the_threshold_and_path_are_configurable(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(
        tmp_path, FAKE_DF_AVAIL_KB=str(20 * 1024 * 1024), DEPLOY_MIN_FREE_GB="30", DEPLOY_DISK_CHECK_PATH="/var/lib"
    )
    assert result.returncode != 0
    assert "only 20.0 GB free on /var/lib, below the 30 GB" in result.stdout
    assert (log_dir / "df-argv").read_text().split() == ["-Pk", "/var/lib"]

    (tmp_path / "off").mkdir()
    off, _ = _run_deploy(tmp_path / "off", FAKE_DF_AVAIL_KB="1", DEPLOY_MIN_FREE_GB="0")
    assert off.returncode == 0, off.stdout + off.stderr


def test_the_disk_path_cannot_inject_into_the_remote_shell(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path, DEPLOY_DISK_CHECK_PATH="/'; touch /tmp/pwned; '")
    assert result.returncode != 0
    assert "DEPLOY_DISK_CHECK_PATH must be an absolute path" in result.stdout
    assert not (log_dir / "ssh-argv").exists()


# --- db: dump first, then recreate, then check the upgrade --------------------


def test_deploy_db_recreates_db_only_after_the_dump(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path, DEPLOY_DB="1")
    assert result.returncode == 0, result.stdout + result.stderr
    events = _events(log_dir)
    dump = _index(events, lambda e: e == "dump")
    recreate = _index(events, lambda e: e.startswith("compose") and e.endswith(" up -d --no-deps db"))
    db_pull = _index(events, lambda e: e.startswith("compose") and e.endswith(" pull db"))
    first_migration = _index(events, lambda e: e == "migrate")
    assert dump < db_pull < recreate < first_migration < _index(events, _is_service_up), events
    # The prepare step before the dump only ever starts a missing db.
    assert all(
        e.endswith(" up -d --no-deps --no-recreate db")
        for e in events[:dump]
        if e.startswith("compose") and " up " in e
    ), events
    assert "Starting mariadb-upgrade" in result.stdout, "the entrypoint's upgrade log must be in the job log"
    assert "MariaDB server 13.0.2, data directory upgraded for 13.0.2." in result.stdout


def test_without_deploy_db_nothing_recreates_db(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    compose_argv = (log_dir / "compose-argv").read_text(encoding="utf-8").splitlines()
    assert not [line for line in compose_argv if line.endswith(" up -d --no-deps db")]
    assert not [line for line in compose_argv if line.endswith(" pull db")]


def test_a_data_directory_left_unupgraded_stops_before_the_migrations(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path, DEPLOY_DB="1", FAKE_UPGRADE_INFO="12.3.3-MariaDB")
    assert result.returncode != 0
    assert "data directory was not upgraded" in result.stdout
    assert "MARIADB_AUTO_UPGRADE" in result.stdout
    events = _events(log_dir)
    assert "dump" in events
    assert "migrate" not in events
    assert not any(_is_service_up(e) for e in events)


def test_a_patch_level_difference_is_not_an_upgrade(tmp_path: Path) -> None:
    """mariadb-upgrade only runs on a major or minor move; 13.0.2 on 13.0.1 data is fine."""
    result, _ = _run_deploy(tmp_path, DEPLOY_DB="1", FAKE_UPGRADE_INFO="13.0.1-MariaDB")
    assert result.returncode == 0, result.stdout + result.stderr


def test_readiness_asks_over_tcp_not_the_upgrade_servers_socket(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path, DEPLOY_DB="1")
    assert result.returncode == 0, result.stdout + result.stderr
    pings = (log_dir / "db-pings").read_text().splitlines()
    assert len(pings) == 2, "one wait in prepare, one after the recreate"
    assert all("--protocol=tcp -h 127.0.0.1 ping" in p for p in pings), pings


def test_deploy_db_without_a_bind_address_warns_about_the_mcp(tmp_path: Path) -> None:
    result, _ = _run_deploy(tmp_path, DEPLOY_DB="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DB_BIND_ADDRESS is not set" in result.stdout
    (tmp_path / "bound").mkdir()
    bound, _ = _run_deploy(tmp_path / "bound", DEPLOY_DB="1", DB_BIND_ADDRESS="198.51.100.7")
    assert "DB_BIND_ADDRESS is not set" not in bound.stdout


def test_the_db_image_is_pinned_by_digest_and_auto_upgrades() -> None:
    compose = yaml.safe_load(PROD_COMPOSE.read_text(encoding="utf-8"))
    db = compose["services"]["db"]
    assert DIGEST_PIN.match(db["image"]), db["image"]
    assert str(db["environment"]["MARIADB_AUTO_UPGRADE"]) == "1"
    for name in ["docker-compose.core.yml", "docker-compose.full.yml", "compose.test.yml"]:
        text = (REPO_ROOT / "docker" / name).read_text(encoding="utf-8")
        images = re.findall(r"^\s*image:\s*(mariadb\S*)", text, flags=re.MULTILINE)
        assert images == [db["image"]], f"{name} runs a different MariaDB: {images}"


def test_renovate_keeps_the_mariadb_digest_current() -> None:
    config = json.loads((REPO_ROOT / "renovate.json").read_text(encoding="utf-8"))
    pinning = [
        rule
        for rule in config["packageRules"]
        if rule.get("pinDigests") and "mariadb" in rule.get("matchPackageNames", [])
    ]
    assert pinning, "renovate.json must pin mariadb's digest"
    assert "docker-compose" in pinning[0]["matchManagers"]
    assert not any(
        rule.get("automerge") and "mariadb" in rule.get("matchPackageNames", ["*"]) for rule in config["packageRules"]
    ), "a MariaDB move must never merge on its own"


# --- image prune after a verified deploy --------------------------------------

RUNNING = "sha256:" + "a" * 64  # music-manager, the current release
PREVIOUS = ["sha256:" + c * 64 for c in "bcd"]  # three previous releases, newest first
OLDEST = "sha256:" + "e" * 64  # a fourth, beyond the rollback window
DANGLING = "sha256:" + "f" * 64  # build leftover without a repository
BACKUP_TOOLS = "sha256:" + "1" * 64  # muma-tools:latest, only run by the nightly backup

FAKE_PRUNE_DOCKER = r"""#!/bin/bash
printf '%s\n' "$*" >> "$FAKE_LOG/docker-argv"
case "$1 $2" in
    "ps -aq") echo c1 ;;
    "inspect --format") printf 'container\t%s\n' "$FAKE_RUNNING" ;;
    "image ls") printf '%s\n' $FAKE_IMAGE_IDS ;;
    "image inspect") cat "$FAKE_LOG/listing" ;;
    rmi*)
        [ "$2" = -f ] && { echo "rmi -f is forbidden" >&2; exit 9; }
        echo "$2" >> "$FAKE_LOG/removed"
        [ "$2" = "$FAKE_RMI_FAILS" ] && { echo "Error: conflict: unable to remove" >&2; exit 1; }
        ;;
esac
exit 0
"""


def _listing() -> str:
    """The inspect-template output for a host after several releases."""
    repo = "muma/music-manager"
    lines = [
        f"image\t{RUNNING}\t2026-09-25T20:00:00.1Z",
        f"tag\t{RUNNING}\t{repo}:latest",
        f"digest\t{RUNNING}\t{repo}@sha256:{'0' * 64}",
    ]
    for day, image_id in zip([24, 23, 22], PREVIOUS, strict=True):
        lines += [f"image\t{image_id}\t2026-09-{day}T20:00:00Z", f"digest\t{image_id}\t{repo}@sha256:{day:064d}"]
    lines += [
        f"image\t{OLDEST}\t2026-09-01T20:00:00Z",
        f"tag\t{OLDEST}\t{repo}:0.60.0",
        f"digest\t{OLDEST}\t{repo}@sha256:{'9' * 64}",
        f"image\t{DANGLING}\t2026-09-20T20:00:00Z",
        f"image\t{BACKUP_TOOLS}\t2026-09-25T19:00:00Z",
        f"tag\t{BACKUP_TOOLS}\tmuma/muma-tools:latest",
    ]
    return "\n".join(lines) + "\n"


def _run_prune(tmp_path: Path, **extra: str) -> tuple[subprocess.CompletedProcess, Path]:
    """Run prune-prod-images.sh against a fake production host."""
    bin_dir, log_dir = _fake_bin(tmp_path)
    (bin_dir / "docker").write_text(FAKE_PRUNE_DOCKER, encoding="utf-8")
    (log_dir / "listing").write_text(_listing(), encoding="utf-8")
    all_ids = [RUNNING, *PREVIOUS, OLDEST, DANGLING, BACKUP_TOOLS]
    env = _env(tmp_path, bin_dir, log_dir, FAKE_RUNNING=RUNNING, FAKE_IMAGE_IDS=" ".join(all_ids), **extra)
    result = subprocess.run(["bash", str(PRUNE_SH)], capture_output=True, text=True, env=env, check=False)
    return result, log_dir


def test_prune_removes_only_what_no_container_and_no_rollback_needs(tmp_path: Path) -> None:
    result, log_dir = _run_prune(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    removed = (log_dir / "removed").read_text().split()
    assert sorted(removed) == sorted(["muma/music-manager:0.60.0", DANGLING])
    assert RUNNING not in removed and not set(PREVIOUS) & set(removed)
    assert "muma/muma-tools:latest" not in removed, "the nightly backup's image has no container between runs"
    assert "2 reference(s) removed, 0 skipped." in result.stdout


def test_prune_never_forces_and_logs_free_space_before_and_after(tmp_path: Path) -> None:
    result, log_dir = _run_prune(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert " -f" not in "".join(line for line in (log_dir / "docker-argv").read_text().splitlines() if "rmi" in line)
    assert "Before: 50.0 GB free on / (50% used)" in result.stdout
    assert "After: 50.0 GB free on / (50% used)" in result.stdout


def test_prune_keep_is_configurable(tmp_path: Path) -> None:
    result, log_dir = _run_prune(tmp_path, PRUNE_KEEP_RELEASES="1")
    assert result.returncode == 0, result.stdout + result.stderr
    removed = set((log_dir / "removed").read_text().split())
    assert removed == {PREVIOUS[1], PREVIOUS[2], "muma/music-manager:0.60.0", DANGLING}


def test_prune_reports_a_refused_removal_and_carries_on(tmp_path: Path) -> None:
    result, _log_dir = _run_prune(tmp_path, FAKE_RMI_FAILS=DANGLING)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"skipped {DANGLING}: Error: conflict" in result.stdout
    assert "1 reference(s) removed, 1 skipped." in result.stdout


def test_prune_dry_run_and_off_switch_remove_nothing(tmp_path: Path) -> None:
    dry, log_dir = _run_prune(tmp_path, PRUNE_DRY_RUN="1")
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "would remove" in dry.stdout and DANGLING in dry.stdout
    assert not (log_dir / "removed").exists()

    (tmp_path / "off").mkdir()
    off, off_log = _run_prune(tmp_path / "off", PRUNE_IMAGES="0")
    assert off.returncode == 0
    assert not (off_log / "docker-argv").exists()


def test_prune_rejects_a_keep_of_zero(tmp_path: Path) -> None:
    result, log_dir = _run_prune(tmp_path, PRUNE_KEEP_RELEASES="0")
    assert result.returncode != 0
    assert not (log_dir / "removed").exists()


def test_ci_deploy_prunes_only_after_verification_and_never_fails_on_it() -> None:
    text = CI_DEPLOY_SH.read_text(encoding="utf-8")
    verify = text.index('"$SCRIPT_DIR/ci/post-deploy-verify.sh"\n')
    prune = text.index('if ! "$SCRIPT_DIR/ci/prune-prod-images.sh"; then')
    assert verify < prune < text.index("CI Deployment finished successfully")
