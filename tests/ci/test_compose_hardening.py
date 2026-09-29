"""Container hardening in the production compose files (issue #32).

Beyond `no-new-privileges`, every production service drops all capabilities and adds back a
named, minimal set, has a PID ceiling, and -- where the image allows it and the test stack proves
it -- a read-only root filesystem. docs/deployment.md ("Container hardening") says why each
service has the set it has and what was deliberately left for later; this pins it, so a new
service cannot arrive unhardened and an existing one cannot quietly regain a capability.

The test stack (docker/compose.test.yml) must carry the same settings on the services it shares
with production: that is what makes core-smoke, core-e2e and the contract suite evidence that the
hardening does not break them, rather than evidence about some other configuration.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROD = ROOT / 'docker' / 'docker-compose.yml'
LMS = ROOT / 'services' / 'music-management-server' / 'docker-compose.yml'
TEST = ROOT / 'docker' / 'compose.test.yml'

ROOT_FILE_CAPS = {'CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'FSETID'}
MARIADB_CAPS = {'CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'SETGID', 'SETUID'}

# service -> expected cap_add (None: no capabilities at all). Services missing from this map
# and not in NO_CAP_DROP fail test_every_service_is_classified.
EXPECTED_CAPS = {
    (PROD, 'db'): MARIADB_CAPS,
    (PROD, 'phpmyadmin'): {'CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'KILL', 'NET_BIND_SERVICE', 'SETGID', 'SETUID'},
    (PROD, 'music-manager'): ROOT_FILE_CAPS,
    (PROD, 'importer_worker'): ROOT_FILE_CAPS,
    (PROD, 'youtube_worker'): ROOT_FILE_CAPS,
    (PROD, 'soundcloud_worker'): ROOT_FILE_CAPS,
    (PROD, 'telegram_worker'): ROOT_FILE_CAPS,
    (PROD, 'soundcloud-fetcher'): ROOT_FILE_CAPS,
    (PROD, 'genre-processor'): ROOT_FILE_CAPS,
    (PROD, 'bpm-analyzer'): ROOT_FILE_CAPS,
    (LMS, 'lms'): ROOT_FILE_CAPS,
    (LMS, 'autoheal'): None,
    (LMS, 'reverse-proxy'): {'CHOWN', 'KILL', 'NET_BIND_SERVICE', 'SETGID', 'SETUID'},
}
# Firefox's s6-overlay init is a follow-up (docs/deployment.md); it only gets a PID ceiling.
NO_CAP_DROP = {(PROD, 'firefox')}

READ_ONLY = {(LMS, 'lms'), (LMS, 'autoheal'), (LMS, 'reverse-proxy')}

# Capabilities no service here needs, whatever else changes.
NEVER = {'NET_RAW', 'NET_ADMIN', 'SYS_ADMIN', 'SYS_PTRACE', 'SYS_MODULE', 'MKNOD', 'SETFCAP', 'SETPCAP', 'ALL'}

# Test-stack service -> the production service whose settings it must mirror.
MIRRORS = {
    'test-db': (PROD, 'db'),
    'music-manager': (PROD, 'music-manager'),
    'music-management-server': (LMS, 'lms'),
}


def _services(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))['services']


def _all_prod_services():
    return [(path, name, svc) for path in (PROD, LMS) for name, svc in _services(path).items()]


def _id(value):
    return value if isinstance(value, str) else ''


@pytest.mark.parametrize('name,svc', [(name, svc) for _, name, svc in _all_prod_services()], ids=_id)
def test_every_service_has_no_new_privileges_and_a_pid_limit(name, svc):
    assert 'no-new-privileges:true' in (svc.get('security_opt') or []), f'{name} lacks no-new-privileges'
    limit = svc.get('pids_limit')
    assert isinstance(limit, int) and 0 < limit <= 4096, f'{name}: pids_limit {limit!r}'


def test_every_service_is_classified():
    unclassified = [
        f'{path.name}:{name}'
        for path, name, _ in _all_prod_services()
        if (path, name) not in EXPECTED_CAPS and (path, name) not in NO_CAP_DROP
    ]
    assert unclassified == [], (
        f'new services need a cap_drop/cap_add decision here and in docs/deployment.md: {unclassified}'
    )


@pytest.mark.parametrize('key', sorted(EXPECTED_CAPS, key=lambda k: (k[0].name, k[1])), ids=lambda k: k[1])
def test_capabilities_are_dropped_and_minimal(key):
    path, name = key
    svc = _services(path)[name]
    assert svc.get('cap_drop') == ['ALL'], f'{name}: cap_drop must be [ALL]'
    added = set(svc.get('cap_add') or [])
    assert added == (EXPECTED_CAPS[key] or set()), f'{name}: cap_add {sorted(added)}'
    assert not added & NEVER


@pytest.mark.parametrize('key', sorted(READ_ONLY, key=lambda k: k[1]), ids=lambda k: k[1])
def test_read_only_services_get_a_bounded_tmp(key):
    path, name = key
    svc = _services(path)[name]
    assert svc.get('read_only') is True
    tmpfs = svc.get('tmpfs') or []
    assert any(entry.startswith('/tmp:size=') for entry in tmpfs), f'{name}: /tmp tmpfs without a size'
    # An unbounded tmpfs is charged to the memory limit until it OOM-kills the container.
    assert all(':size=' in entry for entry in tmpfs), f'{name}: every tmpfs needs a size: {tmpfs}'


def test_reverse_proxy_spools_to_disk_not_memory():
    svc = _services(LMS)['reverse-proxy']
    assert '/var/cache/nginx' in (svc.get('volumes') or [])
    assert not any(entry.startswith('/var/cache/nginx') for entry in svc.get('tmpfs') or [])


def test_no_service_uses_host_networking_or_privileged_mode():
    for _path, name, svc in _all_prod_services():
        assert svc.get('network_mode') != 'host', name
        assert not svc.get('privileged'), name
        assert not svc.get('pid') and not svc.get('ipc'), name


def test_database_ports_stay_on_their_bind_address():
    # 3306 and phpMyAdmin are published on an opt-in address, loopback by default.
    services = _services(PROD)
    assert services['db']['ports'] == ['${DB_BIND_ADDRESS:-127.0.0.1}:3306:3306']
    assert services['phpmyadmin']['ports'] == ['${PHPMYADMIN_BIND_ADDRESS:-127.0.0.1}:8002:80']


@pytest.mark.parametrize('test_name', sorted(MIRRORS))
def test_the_test_stack_runs_the_same_hardening(test_name):
    path, prod_name = MIRRORS[test_name]
    prod, test = _services(path)[prod_name], _services(TEST)[test_name]
    for key in ('cap_drop', 'pids_limit', 'read_only'):
        assert test.get(key) == prod.get(key), f'{test_name}.{key} differs from production {prod_name}'
    assert set(test.get('cap_add') or []) == set(prod.get('cap_add') or [])
    if prod.get('read_only'):
        assert set(test.get('tmpfs') or []) >= set(prod.get('tmpfs') or [])
