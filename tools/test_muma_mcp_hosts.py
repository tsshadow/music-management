"""The host tools, tools/muma_mcp/hosts.py: criterion 7 of the muma-ro design (#176). No network, no ssh."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from tools.muma_mcp import hosts
from tools.muma_mcp.hosts import HostError, HostsConfig

CONFIG = HostsConfig(
    key_dir='/keys',
    known_hosts='/cfg/known_hosts',
    hosts={'prod': 'muma-ro@prod.example.com', 'nas': 'muma-ro@nas.example.com'},
    portainer_url='https://portainer.example.com',
    portainer_token='ptr_view_only_token',
    gitlab_url='https://gitlab.example.com/api/v4',
    gitlab_token='glpat-read-api-token',
)


class FakeSsh:
    """Records whether ssh was started, and with what."""

    def __init__(self, stdout=b'ok\n', stderr=b'', returncode=0):
        self.calls = []
        self.result = SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self.result


def test_the_ssh_argv_pins_every_option():
    argv = hosts.ssh_argv(CONFIG, 'prod', 'uptime')
    assert argv[:3] == ['/usr/bin/ssh', '-i', '/keys/muma-ro-prod_ed25519']
    options = [argv[i + 1] for i, a in enumerate(argv) if a == '-o']
    assert 'BatchMode=yes' in options
    assert 'IdentitiesOnly=yes' in options
    assert 'StrictHostKeyChecking=yes' in options
    assert 'UserKnownHostsFile=/cfg/known_hosts' in options
    assert argv[-4:] == ['-T', 'muma-ro@prod.example.com', '--', 'uptime']


def test_a_refused_string_never_starts_ssh():
    ssh = FakeSsh()
    for command in ('ls /mnt;id', 'ls $(id)', 'ls "/x"', 'ls /x\nid', 'a' * 4097):
        assert hosts.run_on(CONFIG, 'prod', command, ssh).startswith('refused before connecting')
    assert not ssh.calls


def test_an_allowed_string_runs_ssh_without_a_shell_and_masks():
    ssh = FakeSsh(stdout=b'password=hunter22\n', stderr=b'', returncode=0)
    answer = hosts.run_on(CONFIG, 'prod', "ls '/mnt/music'", ssh)
    argv, kwargs = ssh.calls[0]
    assert kwargs['shell'] is False and kwargs['timeout'] == 60
    assert argv[-1] == "ls '/mnt/music'"
    assert 'hunter22' not in answer and '[exit 0]' in answer


def test_a_host_that_is_not_configured_says_which_variable():
    with pytest.raises(HostError, match='MUMA_RO_HOSTS'):
        hosts.ssh_argv(CONFIG, 'proxmox', 'uptime')


def test_a_timeout_is_an_answer_not_an_exception():
    def slow(*_args, **_kwargs):
        raise subprocess.TimeoutExpired('ssh', 60)

    assert 'no answer from prod within 60 s' in hosts.run_on(CONFIG, 'prod', 'uptime', slow)


def test_parse_hosts():
    assert hosts.parse_hosts('prod=muma-ro@prod.example.com, nas=muma-ro@192.0.2.5') == {
        'prod': 'muma-ro@prod.example.com',
        'nas': 'muma-ro@192.0.2.5',
    }
    assert hosts.parse_hosts('') == {}
    for bad in ('laptop=muma-ro@x.example.com', 'prod=root@x;id', 'prod'):
        with pytest.raises(HostError):
            hosts.parse_hosts(bad)


def test_load_needs_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv('MUMA_MCP_CONFIG_DIR', str(tmp_path))
    config = hosts.load({})
    assert config.hosts == {} and config.known_hosts == str(tmp_path / 'known_hosts')


def test_builders_quote_paths_and_check_bounds():
    assert hosts.cmd_ls('/mnt/music/A & B', long=True) == "ls -l '/mnt/music/A & B'"
    assert hosts.cmd_find('/mnt/music', 2, 'f', '*.nfo') == "find '/mnt/music' -maxdepth 2 -type f -name '*.nfo'"
    assert hosts.cmd_container_logs('music-manager', 50, '2h') == 'docker logs --tail 50 --since 2h music-manager'
    assert hosts.cmd_relay(120, 'df -h') == 'pct exec 120 -- df -h'
    for call in (
        lambda: hosts.quote("/mnt/it's"),
        lambda: hosts.cmd_find('/mnt', 4),
        lambda: hosts.cmd_find('/mnt', 1, 'l'),
        lambda: hosts.cmd_container_logs('music-manager', 2001),
        lambda: hosts.cmd_container_logs('music-manager', 5, 'yesterday'),
        lambda: hosts.cmd_journal('a;b'),
        lambda: hosts.name('x y', 'container'),
    ):
        with pytest.raises(HostError):
            call()


class FakeGet:
    """Records the GET and answers with a fixed response."""

    def __init__(self, status=200, text='[]'):
        self.calls = []
        self.response = SimpleNamespace(status_code=status, text=text, ok=200 <= status < 300)

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


@pytest.mark.parametrize('path', ['/api/endpoints/1/docker/containers/json', '/api/stacks', '/api/stacks/3/file'])
def test_portainer_get_allows_the_listed_prefixes(path):
    get = FakeGet()
    hosts.portainer_get(CONFIG, path, get)
    url, kwargs = get.calls[0]
    assert url == f'https://portainer.example.com{path}'
    assert kwargs['headers'] == {'X-API-Key': 'ptr_view_only_token'}


@pytest.mark.parametrize('path', ['/api/users', '/api/auth', 'api/stacks', '/api/stacks/../users', '/api/stacks#x'])
def test_portainer_get_refuses_the_rest(path):
    get = FakeGet()
    with pytest.raises(HostError):
        hosts.portainer_get(CONFIG, path, get)
    assert not get.calls


@pytest.mark.parametrize(
    ('path', 'allowed'),
    [
        ('/projects/12/pipelines?ref=develop', True),
        ('/projects/12/jobs/53013/trace', True),
        ('/projects/group%2Frepo/merge_requests/1423', True),
        ('/projects/12/issues', True),
        ('/runners', True),
        ('/projects/12/variables', False),
        ('/user', False),
        ('/projects/12', False),
    ],
)
def test_gitlab_get_allowlist(path, allowed):
    get = FakeGet()
    if allowed:
        hosts.gitlab_get(CONFIG, path, get)
        assert get.calls[0][1]['headers'] == {'PRIVATE-TOKEN': 'glpat-read-api-token'}
    else:
        with pytest.raises(HostError):
            hosts.gitlab_get(CONFIG, path, get)


def test_an_answer_never_holds_the_token():
    get = FakeGet(text='{"token": "glpat-read-api-token"}')
    assert 'glpat-read-api-token' not in hosts.gitlab_get(CONFIG, '/runners', get)


def test_a_service_without_a_token_is_not_configured():
    with pytest.raises(HostError, match='Proxmox is not configured'):
        hosts.pve_get(CONFIG, '/nodes', FakeGet())


def test_pve_get_adds_the_api_prefix_and_the_token_header():
    config = HostsConfig(pve_url='https://pve.example.com:8006', pve_token='auditor@pve!muma=uuid-value')
    get = FakeGet()
    hosts.pve_get(config, '/cluster/resources', get)
    url, kwargs = get.calls[0]
    assert url == 'https://pve.example.com:8006/api2/json/cluster/resources'
    assert kwargs['headers'] == {'Authorization': 'PVEAPIToken=auditor@pve!muma=uuid-value'}
    with pytest.raises(HostError):
        hosts.pve_get(config, '/access/users', get)
