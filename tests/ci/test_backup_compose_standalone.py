"""docker/docker-compose.backup.yml has to work on its own.

The systemd timers in scripts/backup/systemd/ run it with a single -f, without
the core or tools compose files alongside. docker-compose v1 -- which is what
production runs -- validates the *whole* file before starting any one service,
so a depends_on pointing at a service defined elsewhere makes an unrelated
`run --rm db-backup` die with:

    Service 'soundcloud-fetcher' depends on service 'db' which is undefined.

That is how the first real backup run failed, and it reads as a backup problem
while being a compose-layout problem.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKUP_COMPOSE = ROOT / 'docker' / 'docker-compose.backup.yml'
UNIT_DIR = ROOT / 'scripts' / 'backup' / 'systemd'


def _load(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def test_every_depends_on_target_is_defined_in_the_same_file():
    compose = _load(BACKUP_COMPOSE)
    defined = set(compose['services'])
    for name, service in compose['services'].items():
        for target in service.get('depends_on') or []:
            assert target in defined, (
                f'{name} depends on {target!r}, which this file does not define; '
                'the timers run this compose file standalone')


def test_the_services_the_timers_invoke_exist():
    compose = _load(BACKUP_COMPOSE)
    for unit in sorted(UNIT_DIR.glob('*.service')):
        text = unit.read_text(encoding='utf-8')
        for line in text.splitlines():
            if not line.startswith('ExecStart='):
                continue
            assert 'docker-compose.backup.yml' in line, (
                f'{unit.name} runs a compose file other than the backup one')
            parts = line.split()
            service = parts[parts.index('--rm') + 1]
            assert service in compose['services'], (
                f'{unit.name} runs service {service!r}, which is not defined')


def test_the_tools_compose_no_longer_carries_the_backup_services():
    """They moved out; leaving a copy behind means two definitions drifting."""
    tools = _load(ROOT / 'docker' / 'docker-compose.tools.yml')
    for name in ('db-backup', 'db-restore-check'):
        assert name not in tools['services'], (
            f'{name} is defined in docker-compose.tools.yml as well')


def test_the_backup_services_do_not_write_to_the_dump_directory_read_only():
    """The restore check must never be able to modify what it is checking."""
    compose = _load(BACKUP_COMPOSE)
    volumes = compose['services']['db-restore-check']['volumes']
    backup_mounts = [v for v in volumes if v.endswith(':/backups')
                     or ':/backups:' in v]
    assert backup_mounts, 'db-restore-check has no /backups mount'
    for mount in backup_mounts:
        assert mount.endswith(':ro'), (
            f'{mount} is writable; a restore check that can overwrite its own '
            'source is not a check')
