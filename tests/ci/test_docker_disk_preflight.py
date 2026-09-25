"""The disk pre-flight in front of the emulator job.

On 2026-09-25 mobile:smoke died on the emulator's "Not enough space to create
userdata partition" with 3.7GB left on the workstation's Docker data root, and
the release deploy behind it was skipped (docs/bug-reports/073). The pre-flight
turns that into an early failure that names the fix.
"""

import importlib.util
import sys
from collections import namedtuple
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "docker_disk_preflight.py"
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "test" / "muma-mobile-emulator-smoke.sh"

_spec = importlib.util.spec_from_file_location("docker_disk_preflight", MODULE_PATH)
assert _spec and _spec.loader
preflight = importlib.util.module_from_spec(_spec)
sys.modules["docker_disk_preflight"] = preflight
_spec.loader.exec_module(preflight)

GIB = 1024**3
Usage = namedtuple("Usage", "total used free")


def test_enough_space_passes():
    ok, message = preflight.evaluate(20 * GIB, 183 * GIB, 12 * GIB, "/var/lib/docker", "mobile:smoke")
    assert ok
    assert "OK" in message


def test_exactly_the_minimum_passes():
    ok, _ = preflight.evaluate(12 * GIB, 183 * GIB, 12 * GIB, "/var/lib/docker", "mobile:smoke")
    assert ok


def test_the_incident_fails_and_names_the_fix():
    # 3732.78MB free of 183GB: the numbers from pipeline 3607.
    free = int(3732.78 * 1024**2)
    ok, message = preflight.evaluate(free, 183 * GIB, 12 * GIB, "/var/lib/docker", "mobile:smoke")
    assert not ok
    assert "3.6GB free on /var/lib/docker" in message
    assert "98% used" in message
    assert "mobile:smoke" in message
    assert "disk-janitor.sh" in message
    assert "until=72h" in message


def test_zero_total_does_not_divide_by_zero():
    ok, _ = preflight.evaluate(0, 0, GIB, "/x", "job")
    assert not ok


def test_main_exits_1_when_short(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _path: Usage(100 * GIB, 98 * GIB, 2 * GIB))
    assert preflight.main(["--path", str(tmp_path), "--min-free-gb", "12", "--job", "mobile:smoke"]) == 1
    assert "FAILED" in capsys.readouterr().err


def test_main_exits_0_with_room(monkeypatch, tmp_path):
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _path: Usage(100 * GIB, 50 * GIB, 50 * GIB))
    assert preflight.main(["--path", str(tmp_path), "--min-free-gb", "12"]) == 0


def test_an_uninspectable_path_is_skipped_not_failed(tmp_path, capsys):
    missing = tmp_path / "remote-daemon-root"
    assert preflight.main(["--path", str(missing), "--min-free-gb", "12"]) == 0
    assert "skipped" in capsys.readouterr().out


def test_the_emulator_smoke_runs_the_preflight_before_the_container():
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "docker_disk_preflight.py" in text
    assert text.index("docker_disk_preflight.py") < text.index("docker run")
    assert "EMULATOR_MIN_FREE_GB:-12" in text
