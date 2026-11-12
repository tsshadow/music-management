"""The muma-ro policy loader: criterion 4 of the technical design (issue #176)."""

from __future__ import annotations

import io
import json
import os
import stat
from pathlib import Path

import pytest

from tools.muma_ro import cli
from tools.muma_ro.policy import PolicyError, from_dict, load

POLICIES = Path(__file__).parent / 'muma_ro' / 'policies'


def base(**extra):
    """A minimal valid policy plus ``extra``."""
    return {'class': 'prod', 'verbs': ['ls'], 'roots': [{'path': '/mnt/music', 'mode': 'list'}], **extra}


@pytest.mark.parametrize(
    'path',
    [
        '/',
        '/etc',
        '/etc/muma-ro',
        '/root',
        '/root/x',
        '/home/ops/.ssh',
        '/var/lib/docker/volumes',
        '/etc/gitlab-runner',
    ],
)
def test_a_root_that_holds_secrets_is_refused(path):
    with pytest.raises(PolicyError):
        from_dict(base(roots=[{'path': path, 'mode': 'list'}]))


@pytest.mark.parametrize('path', ['mnt/music', '/mnt/music/', '/mnt/../etc', '/mnt//music'])
def test_a_root_that_is_not_absolute_and_normalized_is_refused(path):
    with pytest.raises(PolicyError):
        from_dict(base(roots=[{'path': path, 'mode': 'list'}]))


@pytest.mark.parametrize(
    'key', ['DB_PASS', 'api_secret', 'GITLAB_TOKEN', 'MUMA_API_KEY', 'X_KEY_Y', 'PRIVATE', 'AWS_CREDENTIALS']
)
def test_an_env_key_that_names_a_secret_is_refused(key):
    with pytest.raises(PolicyError):
        from_dict(base(env_keys=[key]))


@pytest.mark.parametrize(
    'data',
    [
        [],
        {'class': 'laptop', 'verbs': []},
        base(verbs=['ls', 'bash']),
        base(roots=[{'path': '/mnt/music', 'mode': 'write'}]),
        base(units=['sshd']),
        base(containers=['a;b']),
        base(container_patterns=['music-.*']),
        base(container_patterns=['^(unclosed$']),
        base(datasets=['tank/../x']),
        base(head_extensions=['nfo']),
        base(ctids=['10a']),
        base(binaries={'ls': 'ls'}),
        base(verb=['ls']),
    ],
)
def test_a_malformed_policy_is_refused(data):
    with pytest.raises(PolicyError):
        from_dict(data)


def test_every_example_policy_loads():
    names = sorted(p.name for p in POLICIES.glob('*.example.json'))
    assert names == [f'{c}.example.json' for c in ('devvm', 'nas', 'prod', 'proxmox', 'runner')]
    for path in POLICIES.glob('*.example.json'):
        policy = from_dict(json.loads(path.read_text(encoding='utf-8')))
        assert 'help' in policy.verbs


def test_a_group_writable_file_is_refused(tmp_path):
    path = tmp_path / 'policy.json'
    path.write_text(json.dumps(base()), encoding='utf-8')
    path.chmod(path.stat().st_mode | stat.S_IWGRP)  # the file under test must be group writable
    with pytest.raises(PolicyError, match='writable'):
        load(str(path))
    os.chmod(path, 0o644)
    assert load(str(path)).host_class == 'prod'


def test_a_missing_or_broken_file_is_refused(tmp_path):
    with pytest.raises(PolicyError, match='cannot read'):
        load(str(tmp_path / 'absent.json'))
    path = tmp_path / 'policy.json'
    path.write_text('{not json', encoding='utf-8')
    os.chmod(path, 0o644)
    with pytest.raises(PolicyError, match='not valid JSON'):
        load(str(path))


def test_a_policy_that_fails_to_load_refuses_every_command():
    def broken():
        raise PolicyError('root / cannot be a root')

    lines = []
    runtime = cli.Runtime(load_policy=broken, sink=lines.append, popen=_no_process)
    out, err = io.StringIO(), io.StringIO()
    for command in ('help', 'ls /mnt/music', 'uptime'):
        assert cli.serve(command, 'k', helper=False, out=out, err=err, runtime=runtime) == cli.REFUSED_EXIT
    assert out.getvalue() == ''
    assert err.getvalue().count('refused: policy:') == 3
    assert all('"decision": "refused"' in line for line in lines)


def _no_process(*_args, **_kwargs):
    raise AssertionError('nothing may run')
