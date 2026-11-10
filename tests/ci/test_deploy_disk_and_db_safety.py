"""The deploy's disk pre-check and the order around `db`.

Bug report 094. On 2026-09-26 production's root disk was 95% full: every deploy
pulled a new set of images and nothing ever removed the old ones. A pull into a
full disk half-deploys, so the deploy now refuses to start below a free-space
floor. The prune after a verified deploy belongs to the production deploy and
is tested in the operations repository (docs/designs/ops-split/).

The same review found that DEPLOY_DB=1 recreated `db` before the pre-deploy
dump ran, and that the next DEPLOY_DB=1 is a 12.3 -> 13.0 major upgrade with
nothing set to run mariadb-upgrade. These tests run the real scripts against the
fake ssh/docker/compose/df binaries of test_deploy_script_hygiene.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from tests.ci.test_deploy_script_hygiene import (
    REPO_ROOT,
    _events,
    _index,
    _is_service_up,
    _run_deploy,
)

PROD_COMPOSE = REPO_ROOT / "docker" / "docker-compose.yml"
DIGEST_PIN = re.compile(r"^mariadb:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$")


# --- disk pre-check -----------------------------------------------------------


def test_a_nearly_full_disk_stops_the_deploy_before_anything_happens(tmp_path: Path) -> None:
    # 5.5 GB free: the incident's number.
    result, log_dir = _run_deploy(tmp_path, FAKE_DF_AVAIL_KB=str(int(5.5 * 1024 * 1024)))
    assert result.returncode != 0
    assert "only 5.5 GB free on /, below the 8 GB this deploy needs" in result.stdout
    assert "docker image prune" in result.stdout
    events = _events(log_dir)
    assert "dump" not in events and "schema" not in events
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
    schema = _index(events, lambda e: e == "schema")
    assert dump < db_pull < recreate < schema < _index(events, _is_service_up), events
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


def test_a_data_directory_left_unupgraded_stops_before_the_schema_step(tmp_path: Path) -> None:
    result, log_dir = _run_deploy(tmp_path, DEPLOY_DB="1", FAKE_UPGRADE_INFO="12.3.3-MariaDB")
    assert result.returncode != 0
    assert "data directory was not upgraded" in result.stdout
    assert "MARIADB_AUTO_UPGRADE" in result.stdout
    events = _events(log_dir)
    assert "dump" in events
    assert "schema" not in events
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
