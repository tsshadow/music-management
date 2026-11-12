"""How muma-ro runs a command, logs it and hands root work to the helper: criteria 3, 5 and 6 (#176)."""

from __future__ import annotations

import ast
import io
import json
import sys
from pathlib import Path

import pytest

from tools.muma_ro import audit, cli, run
from tools.muma_ro.policy import VERB_NAMES, from_dict
from tools.muma_ro.verbs import Plan

PACKAGE = Path(__file__).parent / 'muma_ro'

POLICY = from_dict(
    {
        'class': 'prod',
        'verbs': list(VERB_NAMES),
        'roots': [{'path': '/mnt/music', 'mode': 'read'}],
        'containers': ['music-manager'],
        'env_keys': ['eps_folder_path'],
        'units': ['muma-db-backup.service'],
        'ctids': ['100'],
    }
)


class FakeProcess:
    """A finished process with fixed output."""

    def __init__(self, stdout=b'', stderr=b'', returncode=0):
        self.stdout_bytes, self.stderr_bytes, self.returncode, self.pid = stdout, stderr, returncode, 4242

    def communicate(self, timeout=None):  # pylint: disable=unused-argument
        """Return the fixed output."""
        return self.stdout_bytes, self.stderr_bytes


class Recorder:
    """A popen stand-in that records every call and returns one FakeProcess."""

    def __init__(self, process=None):
        self.calls: list[tuple[list[str], dict]] = []
        self.process = process or FakeProcess(b'out\n')

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self.process


def runtime(recorder, lines, root=False):
    """A runtime with the test policy, the recorder and a list as audit sink."""
    return cli.Runtime(load_policy=lambda: POLICY, popen=recorder, sink=lines.append, is_root=lambda: root)


def serve(command, recorder, lines, *, helper=False, root=False):
    """Run one request and return (exit, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = cli.serve(command, 'workstation', helper=helper, out=out, err=err, runtime=runtime(recorder, lines, root))
    return code, out.getvalue(), err.getvalue()


# --- criterion 3 ---------------------------------------------------------------------------------


def test_no_module_starts_a_shell():
    """No shell=True, os.system, os.popen, or a subprocess call with a string as its command."""
    for path in PACKAGE.glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == 'shell':
                assert isinstance(node.value, ast.Constant) and node.value.value is False, path
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'os':
                assert node.attr not in ('system', 'popen', 'execl', 'execlp', 'spawnl'), path
            if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], (ast.Constant, ast.JoinedStr)):
                func = ast.unparse(node.func)
                assert not func.startswith('subprocess.'), f'{path}: {func} with a string'


def test_execute_passes_a_list_without_a_shell():
    recorder = Recorder()
    result = run.execute(('/usr/bin/ls', '-1', '--', '/mnt/music'), 30, recorder)
    argv, kwargs = recorder.calls[0]
    assert argv == ['/usr/bin/ls', '-1', '--', '/mnt/music']
    assert kwargs['shell'] is False and kwargs['start_new_session'] is True
    assert kwargs['env'] == {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C.UTF-8'}
    assert kwargs['stdin'] == run.subprocess.DEVNULL
    assert result == run.Result(0, 'out\n', '')


def test_a_timeout_kills_the_group_and_exits_124():
    result = run.execute((sys.executable, '-c', 'import time; time.sleep(30)'), 1)
    assert result.exit_code == run.TIMEOUT_EXIT
    assert 'timed out after 1 s' in result.stderr


def test_a_missing_tool_exits_127_with_a_reason():
    result = run.execute(('/nonexistent/tool',), 30)
    assert result.exit_code == run.NOT_STARTED_EXIT
    assert 'cannot start /nonexistent/tool' in result.stderr


def test_the_self_test_fails_when_an_enabled_tool_is_missing():
    def missing(*_args, **_kwargs):
        raise FileNotFoundError(2, 'No such file or directory')

    out = io.StringIO()
    assert cli.self_test('self-test', out, runtime(missing, [], root=True)) == 1
    assert 'FAIL allowed  uptime (exit 127)' in out.getvalue()


def test_output_is_cut_at_one_mebibyte():
    recorder = Recorder(FakeProcess(b'x' * (run.MAX_OUTPUT_BYTES + 10)))
    result = run.execute(('/usr/bin/true',), 30, recorder)
    assert result.stdout.endswith('output cut at 1 MiB\n')
    assert len(result.stdout) < run.MAX_OUTPUT_BYTES + 100


def test_finish_drops_listed_lines_and_masks():
    plan = Plan('pct-config', (), redact=True, drop_prefixes=('description:', 'sshkeys:'))
    raw = run.Result(
        0, 'arch: amd64\ndescription: secret notes\nsshkeys: ssh-ed25519 AAAA\nenv: DB_PASS=hunter22\n', ''
    )
    assert run.finish(plan, raw).stdout == 'arch: amd64\nenv: DB_PASS=***\n'


# --- serving and the helper (criterion 5) --------------------------------------------------------


def test_an_allowed_command_runs_and_is_logged():
    recorder, lines = Recorder(), []
    code, out, err = serve('ls /mnt/music', recorder, lines)
    assert (code, out, err) == (0, 'out\n', '')
    assert recorder.calls[0][0] == ['/usr/bin/ls', '-1', '--', '/mnt/music']
    entry = json.loads(lines[0])
    assert entry['decision'] == 'allowed' and entry['argv0'] == 'ls' and entry['bytes'] == 4


def test_a_refused_command_exits_2_and_runs_nothing():
    recorder, lines = Recorder(), []
    code, out, err = serve('ls /mnt/music; id', recorder, lines)
    assert code == 2 and out == '' and err.startswith('muma-ro: refused: ')
    assert not recorder.calls
    assert json.loads(lines[0])['decision'] == 'refused'


def test_a_privileged_verb_goes_through_sudo_with_the_original_string():
    recorder, lines = Recorder(), []
    serve('docker logs --tail 5 music-manager', recorder, lines)
    assert recorder.calls[0][0] == [
        '/usr/bin/sudo',
        '-n',
        '/usr/local/libexec/muma-ro-priv',
        '--key',
        'workstation',
        '--command',
        'docker logs --tail 5 music-manager',
    ]


def test_as_root_a_privileged_verb_runs_directly():
    recorder, lines = Recorder(FakeProcess(b'password=hunter22\n')), []
    code, out, _ = serve('docker logs --tail 5 music-manager', recorder, lines, root=True)
    assert code == 0 and out == 'password=***\n'
    assert recorder.calls[0][0][0] == '/usr/bin/docker'


@pytest.mark.parametrize(
    'command',
    [
        'sh',
        'docker run alpine',
        'docker exec music-manager sh',
        'docker exec music-manager printenv',
        'docker logs -f music-manager',
        'find /mnt/music -exec id',
        'ls /mnt/music;id',
        'ls $(id)',
        "docker logs 'music-manager'",
        'docker logs --tail 2001 music-manager',
        'a' * 4097,
        '',
    ],
)
def test_the_helper_refuses_on_its_own(command):
    recorder, lines = Recorder(), []
    code, _, err = serve(command, recorder, lines, helper=True, root=True)
    assert code == 2 and 'refused' in err and not recorder.calls


def test_the_helper_runs_only_privileged_verbs():
    recorder, lines = Recorder(), []
    code, _, err = serve('ls /mnt/music', recorder, lines, helper=True, root=True)
    assert code == 2 and 'only verbs that need root' in err


def test_the_helper_refuses_when_not_root(capsys):
    rt = cli.Runtime(load_policy=lambda: POLICY, popen=Recorder(), sink=lambda _l: None, is_root=lambda: False)
    assert cli.main_priv(['--key', 'k', '--command', 'docker ps'], rt) == 2
    assert 'must run as root' in capsys.readouterr().err


def test_the_helper_takes_no_policy_path():
    with pytest.raises(SystemExit):
        cli.main_priv(['--key', 'k', '--command', 'docker ps', '--policy', '/tmp/p.json'])


def test_main_reads_ssh_original_command(monkeypatch, capsys):
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'uptime')
    monkeypatch.setenv('SSH_CONNECTION', '192.0.2.10 50000 192.0.2.27 22')
    recorder, lines = Recorder(FakeProcess(b' 10:00 up 3 days\n')), []
    assert cli.main(['--key', 'workstation'], runtime(recorder, lines)) == 0
    assert capsys.readouterr().out == ' 10:00 up 3 days\n'
    assert json.loads(lines[0])['client'] == '192.0.2.10'


def test_a_key_name_with_odd_characters_is_refused():
    with pytest.raises(SystemExit):
        cli.main(['--key', 'a;b'])


# --- audit (criterion 6) -------------------------------------------------------------------------


def test_the_audit_line_has_every_field_and_masks_the_command():
    entry = audit.Entry('workstation', '192.0.2.10', 'prod', 'ls', 'ls /x token=abc123', 'allowed', None, 0, 10, 4)
    values = json.loads(audit.line(entry, now=0))
    assert tuple(values) == audit.FIELDS
    assert values['ts'] == '1970-01-01T00:00:00Z'
    assert 'abc123' not in values['command'] and 'token=***' in values['command']


def test_the_audit_line_never_holds_the_output():
    recorder, lines = Recorder(FakeProcess(b'the-secret-output\n')), []
    serve('ls /mnt/music', recorder, lines)
    assert 'the-secret-output' not in lines[0]


def test_the_audit_command_is_cut_at_512_characters():
    entry = audit.Entry('k', 'local', 'prod', 'ls', 'ls /' + 'a' * 2000, 'refused', 'x', 2, 0, 1)
    assert len(json.loads(audit.line(entry))['command']) == 512


# --- self-test -----------------------------------------------------------------------------------


def test_the_self_test_passes_on_a_working_install():
    recorder, lines = Recorder(), []
    out = io.StringIO()
    assert cli.self_test('self-test', out, runtime(recorder, lines, root=True)) == 0
    assert 'FAIL' not in out.getvalue()
    assert "refused  'ls /tmp;id'" in out.getvalue()


def test_the_self_test_fails_when_sudo_asks_for_a_password():
    recorder = Recorder(FakeProcess(b'', b'sudo: a password is required\n', 1))
    out = io.StringIO()
    assert cli.self_test('self-test', out, runtime(recorder, [], root=False)) == 1
    assert 'FAIL allowed  docker ps' in out.getvalue()


def test_the_self_test_refusal_list_covers_the_characters():
    joined = ''.join(cli.MUST_REFUSE)
    for char in (';', '|', '&', '$', '`', '>', '<', '\n', '\x00', '"', '\\'):
        assert char in joined
