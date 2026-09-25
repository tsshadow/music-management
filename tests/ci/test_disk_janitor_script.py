"""What the disk janitor may run against a runner's Docker daemon.

The image selection is covered by test_disk_janitor_plan.py. This file covers
the shell around it, and above all the build cache: on 2026-09-25 124GB of
cache filled the workstation runner to 98% and failed release pipeline 3607
(docs/bug-reports/073), yet an unbounded `docker builder prune` would empty the
ccache that keeps server:unit at ~90s. So every prune must carry an age, and
nothing may prune containers, volumes or the whole system.

Two layers: a static read of the script, which catches a new unbounded prune
line wherever it is added, and a run of the real script against a fake `docker`
and `df` on PATH, which proves the passes fire in the right order at the right
disk levels. Neither touches the real daemon.
"""

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from tests.ci.conftest import load_ci

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "disk-janitor.sh"
SERVICE = REPO_ROOT / "scripts" / "ci" / "systemd" / "muma-disk-janitor.service"


def code_lines() -> list[str]:
    """The script's executable lines: comments and echoed text removed."""
    lines = []
    for raw in SCRIPT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("echo "):
            continue
        lines.append(line)
    return lines


# --- Static policy -----------------------------------------------------------


def test_every_builder_prune_carries_an_age_filter():
    prunes = [line for line in code_lines() if "builder prune" in line]
    assert prunes, "the janitor should prune build cache by age"
    for line in prunes:
        assert re.search(r'--filter "until=\$\{?\w+\}?h"', line), line
        assert "--all" not in line and not re.search(r"\s-a\b", line), line


def test_no_unbounded_or_foreign_prune():
    code = "\n".join(code_lines())
    for forbidden in ("system prune", "volume prune", "container prune", "network prune", "rmi -f", "buildx prune"):
        assert forbidden not in code, forbidden
    for line in code_lines():
        if "image prune" in line:
            assert "--all" not in line and not re.search(r"\s-a\b", line), line


def test_default_cache_ages_are_72h_and_a_24h_floor():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'CACHE_MAX_AGE="${DISK_JANITOR_CACHE_MAX_AGE_HOURS:-72}"' in text
    assert 'CACHE_FLOOR_AGE="${DISK_JANITOR_CACHE_FLOOR_AGE_HOURS:-24}"' in text


def test_the_ci_job_and_the_timer_run_the_script_without_overrides():
    # An override here (say --cache-max-age 1) would quietly defeat the age
    # filter on one host; the defaults are the reviewed policy.
    job = load_ci()["runner:disk-janitor"]
    assert job["script"] == ["./scripts/ci/disk-janitor.sh"]
    exec_start = next(line for line in SERVICE.read_text().splitlines() if line.startswith("ExecStart="))
    assert exec_start == "ExecStart=/opt/muma-disk-janitor/disk-janitor.sh"


# --- Behaviour against a fake daemon -----------------------------------------

FAKE_DOCKER = r"""#!/bin/bash
# Logs every call; `builder prune` lowers the fake disk usage.
echo "$*" >> "$STATE/calls"
case "$1" in
    info) echo "$STATE/root" ;;
    builder)
        if [ "$2" = "prune" ]; then
            next="$(head -n 1 "$STATE/after_prune" 2>/dev/null)"
            if [ -n "$next" ]; then
                echo "$next" > "$STATE/usage"
                tail -n +2 "$STATE/after_prune" > "$STATE/after_prune.tmp"
                mv "$STATE/after_prune.tmp" "$STATE/after_prune"
            fi
            echo "Total reclaimed space: 1GB"
        fi ;;
esac
exit 0
"""

FAKE_DF = r"""#!/bin/bash
pct="$(cat "$STATE/usage")"
echo "Filesystem 1024-blocks Used Available Capacity Mounted on"
echo "/dev/fake 1000 ${pct}0 $((100 - pct))0 ${pct}% $STATE/root"
"""


def _executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_janitor(tmp_path: Path, usage: int, after_prunes: list[int], *args: str) -> tuple[int, list[str], str]:
    """Run the real script with fake docker/df; return (exit, docker calls, output)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "root").mkdir()
    _executable(bin_dir / "docker", FAKE_DOCKER)
    _executable(bin_dir / "df", FAKE_DF)
    (tmp_path / "usage").write_text(f"{usage}\n")
    (tmp_path / "after_prune").write_text("".join(f"{value}\n" for value in after_prunes))
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STATE": str(tmp_path)}
    env.pop("DISK_JANITOR_CACHE_MAX_AGE_HOURS", None)
    env.pop("DISK_JANITOR_CACHE_FLOOR_AGE_HOURS", None)
    result = subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=60, check=False
    )
    calls_file = tmp_path / "calls"
    calls = calls_file.read_text().splitlines() if calls_file.exists() else []
    return result.returncode, calls, result.stdout + result.stderr


def prunes(calls: list[str]) -> list[str]:
    return [call for call in calls if call.startswith("builder prune")]


def test_below_threshold_prunes_nothing(tmp_path):
    code, calls, _ = run_janitor(tmp_path, 50, [])
    assert code == 0
    assert prunes(calls) == []


def test_a_full_disk_loses_only_cache_older_than_72h_when_that_is_enough(tmp_path):
    code, calls, output = run_janitor(tmp_path, 98, [60])
    assert code == 0
    assert prunes(calls) == ["builder prune -f --filter until=72h"]
    assert "Before:" in output and "After:" in output
    assert calls.count("system df") == 2


def test_still_critical_after_the_age_prune_drops_to_the_24h_floor(tmp_path):
    code, calls, _ = run_janitor(tmp_path, 98, [90, 70])
    assert code == 0
    assert prunes(calls) == [
        "builder prune -f --filter until=72h",
        "builder prune -f --filter until=24h",
    ]


def test_still_critical_after_the_floor_asks_for_a_human(tmp_path):
    code, calls, output = run_janitor(tmp_path, 98, [95, 92])
    assert code == 1
    assert len(prunes(calls)) == 2
    assert "decide that knowingly" in output


def test_ages_are_configurable(tmp_path):
    _, calls, _ = run_janitor(tmp_path, 98, [90, 70], "--cache-max-age", "48", "--cache-floor-age", "12")
    assert prunes(calls) == [
        "builder prune -f --filter until=48h",
        "builder prune -f --filter until=12h",
    ]


@pytest.mark.parametrize("age", ["0", "00", "", "3d", "-5"])
def test_an_age_that_would_mean_everything_is_refused(tmp_path, age):
    code, calls, _ = run_janitor(tmp_path, 98, [], "--cache-max-age", age)
    assert code == 2
    assert prunes(calls) == []


def test_dry_run_prunes_nothing(tmp_path):
    code, calls, output = run_janitor(tmp_path, 98, [], "--dry-run")
    assert code == 0
    assert prunes(calls) == []
    assert "until=72h" in output
    assert not any(call.startswith(("rmi", "image prune")) for call in calls)
