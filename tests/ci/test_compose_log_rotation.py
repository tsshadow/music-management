"""Every compose service has a size-capped json-file log.

Docker's default logging driver is json-file *without* a size cap, so a
container that is never recreated grows its log under /var/lib/docker until
the disk is full. On the production host a full disk has already presented as
an unrelated 502 (docs/bug-reports/081-compose-logs-grow-without-bound.md).

The compose files are discovered by glob rather than listed, so a compose file
added later is covered without anyone remembering this test exists.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = sorted(
    {
        *ROOT.glob("docker/*compose*.yml"),
        *ROOT.glob("services/*/docker-compose*.yml"),
    }
)

# Generous upper bounds: a container may get more room than the default, but
# not so much that one of them can fill the root filesystem on its own.
MAX_FILE_MB = 50
MAX_FILES = 10


def _load(path: Path) -> dict:
    """Parse one compose file with its YAML anchors resolved."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _megabytes(size: str) -> float:
    """Docker's max-size notation (`10m`, `512k`, `1g`) in megabytes."""
    units = {"k": 1 / 1024, "m": 1, "g": 1024}
    size = str(size).strip().lower()
    if size[-1] in units:
        return float(size[:-1]) * units[size[-1]]
    return float(size) / (1024 * 1024)


def _ids(path: Path) -> str:
    return str(path.relative_to(ROOT))


def test_the_known_compose_files_are_discovered():
    """Guards the glob itself: an empty list would make every test below pass."""
    found = {_ids(path) for path in COMPOSE_FILES}
    for expected in (
        "docker/docker-compose.yml",
        "docker/docker-compose.backup.yml",
        "docker/compose.test.yml",
        "services/music-management-server/docker-compose.yml",
    ):
        assert expected in found


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=_ids)
def test_every_service_logs_to_a_rotated_json_file(path: Path):
    services = _load(path).get("services") or {}
    assert services, f"{_ids(path)} defines no services"
    for name, service in services.items():
        logging = (service or {}).get("logging")
        assert logging, f"{_ids(path)}: service {name!r} has no logging block (use *default-logging)"
        assert logging.get("driver") == "json-file", f"{_ids(path)}: {name!r} logs through {logging.get('driver')!r}"
        options = logging.get("options") or {}
        assert "max-size" in options and "max-file" in options, (
            f"{_ids(path)}: {name!r} has json-file logging without max-size/max-file, which does not rotate"
        )
        assert _megabytes(options["max-size"]) <= MAX_FILE_MB, f"{_ids(path)}: {name!r} max-size too large"
        assert 1 <= int(options["max-file"]) <= MAX_FILES, f"{_ids(path)}: {name!r} max-file out of range"


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=_ids)
def test_extension_fields_need_a_file_format_that_allows_them(path: Path):
    """Production runs docker-compose v1: `x-` fields need format 3.4+ (or no version, the Compose spec)."""
    document = _load(path)
    if not any(str(key).startswith("x-") for key in document):
        return
    version = document.get("version")
    if version is None:
        return
    major, _, minor = str(version).partition(".")
    assert (int(major), int(minor or 0)) >= (3, 4), f"{_ids(path)} uses x- fields with version {version}"
