"""The muma-ro parser and verb grammar: criteria 1 and 2 of the technical design (issue #176)."""

from __future__ import annotations

import pytest

from tools.muma_ro import policy as policy_module
from tools.muma_ro.parse import MAX_COMMAND_BYTES, Refused, Token, check_characters, tokenize
from tools.muma_ro.policy import VERB_NAMES, from_dict
from tools.muma_ro.verbs import VERBS, Context, Plan, build, verb_of

POLICY = from_dict(
    {
        'class': 'prod',
        'verbs': list(VERB_NAMES),
        'roots': [{'path': '/mnt/music', 'mode': 'read'}, {'path': '/mnt/backups/muma', 'mode': 'list'}],
        'containers': ['music-manager'],
        'container_patterns': ['^music-management-[a-z0-9-]+$'],
        'env_keys': ['eps_folder_path'],
        'units': ['muma-db-backup.service'],
        'head_extensions': ['.nfo', '.txt'],
        'datasets': ['tank/music'],
        'ctids': ['100'],
    }
)


def plan_for(command: str, policy: policy_module.Policy = POLICY) -> Plan:
    """Parse and build ``command`` against ``policy``."""
    return build(tokenize(command), Context(policy, 'workstation', command))


def refusal(command: str, policy: policy_module.Policy = POLICY) -> str:
    """The reason ``command`` is refused; fails the test when it is allowed."""
    with pytest.raises(Refused) as caught:
        plan_for(command, policy)
    return str(caught.value)


def test_every_verb_has_a_builder():
    assert set(VERBS) == set(VERB_NAMES)


@pytest.mark.parametrize(
    ('command', 'reason'),
    [
        ('ls /mnt/music/..', '..'),
        ('ls /mnt/music/../etc', '..'),
        ('ls ../mnt/music', 'absolute'),
        ('ls /mnt/music/EPs/../../etc', '..'),
        ('ls /mnt/musicx', 'outside every root'),
        ('ls mnt/music', 'absolute'),
        ('head /mnt/backups/muma/dump.txt', 'may be listed, not read'),
        ('head /mnt/music/EPs/track.flac', 'head reads only'),
    ],
)
def test_paths_are_refused(command, reason):
    assert reason in refusal(command)


def test_a_link_under_a_root_that_points_outside_is_refused(tmp_path):
    root = tmp_path / 'music'
    root.mkdir()
    outside = tmp_path / 'secret'
    outside.mkdir()
    (root / 'escape').symlink_to(outside)
    policy = from_dict({'class': 'prod', 'verbs': ['ls'], 'roots': [{'path': str(root), 'mode': 'read'}]})
    assert 'outside every root' in refusal(f'ls {root}/escape', policy)
    assert plan_for(f'ls {root}', policy).argv[-1] == str(root)


@pytest.mark.parametrize(
    'command',
    [
        'sh',
        'bash',
        'python3',
        'rm /mnt/music/x',
        'cat /mnt/music/x.nfo',
        'docker run alpine',
        'docker cp music-manager:/x /mnt/music',
        'docker exec music-manager sh',
        'docker exec music-manager printenv',
        'docker logs -f music-manager',
        'docker logs --follow music-manager',
        'find /mnt/music -exec id',
        'find /mnt/music -delete',
        'find /mnt/music -fprint /mnt/music/x',
        'zfs destroy tank/music',
        'zfs set compression=off tank/music',
        'zpool scrub tank',
        'pct set 100',
        'pct start 100',
        'qm stop 100',
        'pvesh get /nodes',
        'midclt call system.info',
        'systemctl restart muma-db-backup.service',
    ],
)
def test_verbs_outside_the_grammar_are_refused(command):
    refusal(command)


@pytest.mark.parametrize(
    ('command', 'reason'),
    [
        ('ls /mnt/music;id', "';'"),
        ('ls /mnt/music | id', "'|'"),
        ('ls /mnt/music && id', "'&'"),
        ('ls $(id)', "'$'"),
        ('ls `id`', "'`'"),
        ('ls /mnt/music > /mnt/music/x', "'>'"),
        ('ls < /mnt/music/x', "'<'"),
        ('ls /mnt/music\nid', 'newline'),
        ('ls /mnt/music\rid', 'carriage return'),
        ('ls /mnt/music\x00', 'NUL'),
        ('ls "/mnt/music"', 'double quote'),
        ('ls \\/mnt/music', 'backslash'),
        ("ls '/mnt/music", 'unterminated'),
        ('ls /mnt/music\tid', "'\\t'"),
        ('ls /mnt/music*', "'*'"),
        ('ls ~', "'~'"),
        ("ls '/mnt/music/\x07'", 'control character'),
    ],
)
def test_characters_are_refused(command, reason):
    assert reason in refusal(command)


@pytest.mark.parametrize(
    'command',
    [
        "docker logs '--tail' 5 music-manager",
        "docker logs 'music-manager'",
        "docker exec music-manager printenv 'eps_folder_path'",
        "journalctl -u 'muma-db-backup.service'",
        "'ls' /mnt/music",
        "head -n '5' /mnt/music/a.nfo",
    ],
)
def test_a_quoted_token_outside_a_path_or_pattern_is_refused(command):
    reason = refusal(command)
    assert 'quoted' in reason or 'not a muma-ro verb' in reason


@pytest.mark.parametrize(
    ('command', 'reason'),
    [
        ('docker logs --tail 2001 music-manager', '0 to 2000'),
        ('find /mnt/music -maxdepth 4', '0 to 3'),
        ('head -n 201 /mnt/music/a.nfo', '0 to 200'),
        ('journalctl -u muma-db-backup.service -n 501', '0 to 500'),
        ('docker exec music-manager printenv DB_PASS', 'not on this host'),
        ('docker logs other-container', 'not on this host'),
        ('journalctl -u ssh.service', 'not on this host'),
        ('zfs list other/pool', 'not on this host'),
        ('zfs list tank/music/../other', 'not on this host'),
        ('pct config 999', 'not on this host'),
        ('docker logs --since yesterday music-manager', 'duration'),
        ('vzdump-log ../../etc/shadow', 'usage'),
        ('a' * (MAX_COMMAND_BYTES + 1), 'longer than'),
        ('', 'no command'),
        ('   ', 'no command'),
    ],
)
def test_values_are_refused(command, reason):
    assert reason in refusal(command)


def test_a_verb_the_host_does_not_enable_is_refused():
    policy = from_dict({'class': 'nas', 'verbs': ['ls'], 'roots': [{'path': '/mnt/tank', 'mode': 'list'}]})
    assert 'not enabled on this host' in refusal('docker ps', policy)


def test_a_quoted_path_is_one_argument():
    plan = plan_for("ls '/mnt/music/EPs/Artist & Artist (Live)'")
    assert plan.argv[-1] == '/mnt/music/EPs/Artist & Artist (Live)'
    assert plan.argv[:2] == ('/usr/bin/ls', '-1')


def test_tokenize_keeps_quoted_spaces_and_marks_the_token():
    assert tokenize("ls -l '/a b'") == [Token('ls'), Token('-l'), Token('/a b', quoted=True)]


def test_a_quoted_glob_reaches_find_as_one_argument():
    plan = plan_for("find /mnt/music -maxdepth 2 -type f -name '*.nfo'")
    assert plan.argv[1:] == ('/mnt/music', '-maxdepth', '2', '-type', 'f', '-name', '*.nfo')
    assert plan.timeout == 120


def test_check_characters_accepts_the_plain_set():
    check_characters('ls -l /mnt/music/EPs_1.2:a=b@c+d,e%f-g')


@pytest.mark.parametrize(
    ('command', 'argv'),
    [
        ('docker ps', ('/usr/bin/docker', 'ps', '--format')),
        ('docker system df', ('/usr/bin/docker', 'system', 'df')),
        ('systemctl list-timers', ('/usr/bin/systemctl', 'list-timers')),
        ('docker logs --tail 5 music-management-lms', ('/usr/bin/docker', 'logs', '--tail', '5')),
        ('zfs list -t snapshot tank/music', ('/usr/sbin/zfs', 'list', '-H')),
        ('pct config 100', ('/usr/sbin/pct', 'config', '100')),
    ],
)
def test_allowed_commands_build_a_fixed_argv(command, argv):
    plan = plan_for(command)
    assert plan.argv[: len(argv)] == argv


def test_docker_inspect_never_asks_for_the_environment():
    template = plan_for('docker inspect music-manager').argv[3]
    assert 'Env' not in template


def test_logs_and_config_are_masked():
    assert plan_for('docker logs music-manager').redact
    assert plan_for('journalctl -u muma-db-backup.service').redact
    config = plan_for('pct config 100')
    assert config.redact and 'description:' in config.drop_prefixes


def test_privileged_verbs_are_marked():
    assert plan_for('docker ps').privileged
    assert plan_for('pct list').privileged
    assert not plan_for('ls /mnt/music').privileged


def test_the_relay_hands_the_inner_string_to_the_containers_own_wrapper():
    plan = plan_for("pct exec 100 -- ls -l '/srv/a b'")
    assert plan.argv == (
        '/usr/sbin/pct',
        'exec',
        '100',
        '--',
        '/usr/local/bin/muma-ro',
        '--key',
        'relay-workstation',
        '--command',
        "ls -l '/srv/a b'",
    )


def test_the_relay_refuses_an_unlisted_id():
    assert 'not on this host' in refusal('pct exec 101 -- ls /')


def test_help_lists_the_enabled_verbs_and_roots():
    text = plan_for('help').text
    assert text and 'docker logs' in text and '/mnt/music (read)' in text


def test_verb_of_names_two_word_verbs():
    assert verb_of(tokenize('docker ps -a'))[0] == 'docker-ps'
    assert verb_of(tokenize('vzdump-log a.log'))[0] == 'vzdump-log'
    with pytest.raises(Refused):
        verb_of(tokenize('docker-ps'))
