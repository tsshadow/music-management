"""One builder per verb: check the arguments, return the fixed argument list to run.

A builder never copies a flag from the agent's text into the argument list. It recognizes the
flags its grammar has, and writes its own. Everything else is refused. The grammar per verb is the
table "Verbs Per Host Class" in the technical design; ``help`` prints it per host.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from tools.muma_ro.parse import Refused, Token, check_characters
from tools.muma_ro.policy import VERB_NAMES, Policy

DEFAULT_TIMEOUT = 30
SLOW_TIMEOUT = 120

BINARIES = {
    'ls': '/usr/bin/ls',
    'stat': '/usr/bin/stat',
    'find': '/usr/bin/find',
    'head': '/usr/bin/head',
    'tail': '/usr/bin/tail',
    'du': '/usr/bin/du',
    'df': '/usr/bin/df',
    'free': '/usr/bin/free',
    'uptime': '/usr/bin/uptime',
    'docker': '/usr/bin/docker',
    'systemctl': '/usr/bin/systemctl',
    'journalctl': '/usr/bin/journalctl',
    'zfs': '/usr/sbin/zfs',
    'zpool': '/usr/sbin/zpool',
    'getfacl': '/usr/bin/getfacl',
    'pct': '/usr/sbin/pct',
    'qm': '/usr/sbin/qm',
    'pvesm': '/usr/sbin/pvesm',
}

MUMA_RO = '/usr/local/bin/muma-ro'
VZDUMP_LOG_DIR = '/var/log/vzdump'
DEFAULT_ZFS_PROPERTIES = frozenset(
    {'used', 'available', 'referenced', 'compression', 'compressratio', 'mountpoint', 'quota', 'recordsize'}
)
# Lines of `pct config` / `qm config` that can hold a secret or free text.
CONFIG_SECRET_PREFIXES = ('description:', 'cipassword:', 'sshkeys:', '#')

_DURATION = re.compile(r'^([0-9]{1,6})([smhd])$')
_GLOB = re.compile(r'^[^/\x00-\x1f]{1,128}$')
_JOURNAL_UNITS = {'s': 's', 'm': 'min', 'h': 'h', 'd': 'd'}
_VZDUMP_FILE = re.compile(r'^[A-Za-z0-9._-]{1,128}\.log$')


@dataclass(frozen=True)
class Plan:
    """What to run for one allowed command."""

    verb: str
    argv: tuple[str, ...]
    timeout: int = DEFAULT_TIMEOUT
    privileged: bool = False
    redact: bool = False
    drop_prefixes: tuple[str, ...] = ()
    text: str | None = None  # a verb answered without running anything (help)


@dataclass(frozen=True)
class Context:
    """What a builder needs besides the arguments: the policy and the caller's key name."""

    policy: Policy
    key: str
    command: str


Builder = Callable[[list[Token], Context], Plan]


# --- argument kinds ------------------------------------------------------------------------------


def plain(token: Token, what: str) -> str:
    """A token that may not be quoted: only a path or a glob may be."""
    if token.quoted:
        raise Refused(f'a quoted {what}; only a path or a name pattern may be quoted')
    return token.text


def number(token: Token, what: str, maximum: int) -> str:
    """Digits only, at most ``maximum``."""
    text = plain(token, what)
    if not text.isdigit() or int(text) > maximum:
        raise Refused(f'{what} must be a number from 0 to {maximum}')
    return str(int(text))


def duration(token: Token) -> tuple[int, str]:
    """``[0-9]+[smhd]``, for ``--since``."""
    match = _DURATION.match(plain(token, 'duration'))
    if not match:
        raise Refused('a duration looks like 30m, 2h or 1d')
    return int(match.group(1)), match.group(2)


def check_path(token: Token, policy: Policy, mode: str) -> str:
    """An absolute path whose real location is a root of the policy, or below one, in ``mode``.

    ``mode`` ``list`` needs any root; ``read`` needs a root with mode ``read``. Symbolic links are
    followed first, so a link under a root that points outside it is refused.
    """
    path = token.text
    if not path.startswith('/'):
        raise Refused('a path must be absolute')
    if '..' in path.split('/'):
        raise Refused('a path may not contain ..')
    real = os.path.realpath(path)
    for root in policy.roots:
        base = os.path.realpath(root.path)
        if real == base or real.startswith(base.rstrip('/') + '/'):
            if mode == 'read' and root.mode != 'read':
                raise Refused(f'{root.path} may be listed, not read')
            return real
    raise Refused('the path is outside every root of this host')


def container(token: Token, policy: Policy) -> str:
    """A container name the policy lists or matches."""
    name = plain(token, 'container name')
    if not policy.allows_container(name):
        raise Refused(f'container {name} is not on this host\'s list')
    return name


def unit(token: Token, policy: Policy) -> str:
    """A systemd unit the policy lists."""
    name = plain(token, 'unit')
    if name not in policy.units:
        raise Refused(f'unit {name} is not on this host\'s list')
    return name


def dataset(token: Token, policy: Policy) -> str:
    """A ZFS dataset (or snapshot of one) equal to or below a listed dataset."""
    name = plain(token, 'dataset')
    base = name.split('@', 1)[0]
    if '..' in base.split('/') or '.' in base.split('/') or not policy.allows_dataset(base):
        raise Refused(f'dataset {name} is not on this host\'s list')
    return name


def ctid(token: Token, policy: Policy) -> str:
    """A Proxmox container or VM id the policy lists."""
    value = plain(token, 'container id')
    if value not in policy.ctids:
        raise Refused(f'id {value} is not on this host\'s list')
    return value


def no_more(args: Sequence[Token]) -> None:
    """Refuse leftover arguments."""
    if args:
        raise Refused(f'unexpected argument {args[0].text!r}')


def binary(ctx: Context, name: str) -> str:
    """The absolute path of a tool: the policy's override, else the default."""
    return ctx.policy.binaries.get(name, BINARIES[name])


# --- file system ---------------------------------------------------------------------------------


def build_ls(args: list[Token], ctx: Context) -> Plan:
    """``ls [-l] [-a] PATH``."""
    flags: list[str] = []
    while args and not args[0].quoted and args[0].text in ('-l', '-a', '-la', '-al'):
        flags.extend(f'-{c}' for c in args.pop(0).text[1:] if f'-{c}' not in flags)
    if len(args) != 1:
        raise Refused('usage: ls [-l] [-a] PATH')
    path = check_path(args[0], ctx.policy, 'list')
    return Plan('ls', (binary(ctx, 'ls'), '-1', *flags, '--', path))


def build_stat(args: list[Token], ctx: Context) -> Plan:
    """``stat PATH``."""
    if len(args) != 1:
        raise Refused('usage: stat PATH')
    return Plan('stat', (binary(ctx, 'stat'), '--', check_path(args[0], ctx.policy, 'list')))


def build_find(args: list[Token], ctx: Context) -> Plan:
    """``find PATH [-maxdepth N<=3] [-type f|d] [-name GLOB]``. No action flags exist here."""
    if not args:
        raise Refused('usage: find PATH [-maxdepth N] [-type f|d] [-name GLOB]')
    path = check_path(args.pop(0), ctx.policy, 'list')
    depth, kind, name = '1', None, None
    while args:
        flag = plain(args.pop(0), 'find option')
        if not args:
            raise Refused(f'{flag} needs a value')
        value = args.pop(0)
        if flag == '-maxdepth':
            depth = number(value, '-maxdepth', 3)
        elif flag == '-type' and plain(value, '-type') in ('f', 'd'):
            kind = value.text
        elif flag == '-name' and _GLOB.match(value.text) and value.text.isprintable():
            name = value.text
        else:
            raise Refused(f'find option {flag} is not allowed (only -maxdepth, -type f|d, -name)')
    argv = [binary(ctx, 'find'), path, '-maxdepth', depth]
    if kind:
        argv += ['-type', kind]
    if name:
        argv += ['-name', name]
    return Plan('find', tuple(argv), timeout=SLOW_TIMEOUT)


def build_head(args: list[Token], ctx: Context) -> Plan:
    """``head [-n N<=200] PATH`` of a file with a listed extension under a ``read`` root."""
    lines = '50'
    if len(args) == 3 and plain(args[0], 'head option') == '-n':
        lines = number(args[1], '-n', 200)
        args = args[2:]
    if len(args) != 1:
        raise Refused('usage: head [-n N] PATH')
    path = check_path(args[0], ctx.policy, 'read')
    if not path.lower().endswith(ctx.policy.head_extensions) or not ctx.policy.head_extensions:
        raise Refused(f'head reads only {", ".join(ctx.policy.head_extensions) or "no"} files here')
    return Plan('head', (binary(ctx, 'head'), '-n', lines, '--', path))


def build_du(args: list[Token], ctx: Context) -> Plan:
    """``du -s PATH``."""
    if len(args) != 2 or plain(args[0], 'du option') != '-s':
        raise Refused('usage: du -s PATH')
    return Plan('du', (binary(ctx, 'du'), '-s', '--', check_path(args[1], ctx.policy, 'list')), timeout=SLOW_TIMEOUT)


def build_df(args: list[Token], ctx: Context) -> Plan:
    """``df [-h] [PATH]``."""
    argv = [binary(ctx, 'df')]
    if args and not args[0].quoted and args[0].text == '-h':
        argv.append('-h')
        args = args[1:]
    if len(args) > 1:
        raise Refused('usage: df [-h] [PATH]')
    if args:
        argv += ['--', check_path(args[0], ctx.policy, 'list')]
    return Plan('df', tuple(argv))


def build_free(args: list[Token], ctx: Context) -> Plan:
    """``free -m``."""
    if [plain(a, 'option') for a in args] not in ([], ['-m']):
        raise Refused('usage: free -m')
    return Plan('free', (binary(ctx, 'free'), '-m'))


def build_uptime(args: list[Token], ctx: Context) -> Plan:
    """``uptime``."""
    no_more(args)
    return Plan('uptime', (binary(ctx, 'uptime'),))


def build_getfacl(args: list[Token], ctx: Context) -> Plan:
    """``getfacl PATH``."""
    if len(args) != 1:
        raise Refused('usage: getfacl PATH')
    return Plan('getfacl', (binary(ctx, 'getfacl'), '--', check_path(args[0], ctx.policy, 'list')))


# --- docker --------------------------------------------------------------------------------------


def build_docker_ps(args: list[Token], ctx: Context) -> Plan:
    """``docker ps [-a]``, with a fixed output format."""
    show_all = [plain(a, 'option') for a in args]
    if show_all not in ([], ['-a']):
        raise Refused('usage: docker ps [-a]')
    argv = [binary(ctx, 'docker'), 'ps', *show_all, '--format', '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.CreatedAt}}']
    return Plan('docker-ps', tuple(argv), privileged=True)


def build_docker_logs(args: list[Token], ctx: Context) -> Plan:
    """``docker logs [--tail N<=2000] [--since D] C``; never ``-f``; the output is masked."""
    tail, since = '200', None
    while len(args) > 1:
        flag = plain(args.pop(0), 'docker logs option')
        if flag == '--tail':
            tail = number(args.pop(0), '--tail', 2000)
        elif flag == '--since':
            amount, letter = duration(args.pop(0))
            since = f'{amount}{letter}'
        else:
            raise Refused(f'docker logs option {flag} is not allowed (only --tail N, --since D)')
    if len(args) != 1:
        raise Refused('usage: docker logs [--tail N] [--since D] CONTAINER')
    argv = [binary(ctx, 'docker'), 'logs', '--tail', tail]
    if since:
        argv += ['--since', since]
    argv.append(container(args[0], ctx.policy))
    return Plan('docker-logs', tuple(argv), privileged=True, redact=True)


def build_docker_inspect(args: list[Token], ctx: Context) -> Plan:
    """``docker inspect C``: state, health, restarts, image and mounts. Never the environment."""
    if len(args) != 1:
        raise Refused('usage: docker inspect CONTAINER')
    template = (
        '{{.Name}} {{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} '
        'restarts={{.RestartCount}} started={{.State.StartedAt}} image={{.Config.Image}}\n'
        '{{range .Mounts}}{{.Source}} -> {{.Destination}} rw={{.RW}}\n{{end}}'
    )
    argv = (binary(ctx, 'docker'), 'inspect', '--format', template, container(args[0], ctx.policy))
    return Plan('docker-inspect', argv, privileged=True)


def build_docker_stats(args: list[Token], ctx: Context) -> Plan:
    """``docker stats``, one sample."""
    no_more(args)
    template = '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}'
    return Plan('docker-stats', (binary(ctx, 'docker'), 'stats', '--no-stream', '--format', template), privileged=True)


def build_docker_system_df(args: list[Token], ctx: Context) -> Plan:
    """``docker system df``."""
    no_more(args)
    return Plan('docker-system-df', (binary(ctx, 'docker'), 'system', 'df'), privileged=True)


def build_docker_printenv(args: list[Token], ctx: Context) -> Plan:
    """``docker exec C printenv KEY``, the key from the policy's list."""
    if len(args) != 3 or plain(args[1], 'docker exec command') != 'printenv':
        raise Refused('usage: docker exec CONTAINER printenv KEY; nothing else runs in a container')
    name = container(args[0], ctx.policy)
    key = plain(args[2], 'env key')
    if key not in ctx.policy.env_keys:
        raise Refused(f'env key {key} is not on this host\'s list')
    return Plan('docker-printenv', (binary(ctx, 'docker'), 'exec', name, 'printenv', key), privileged=True)


# --- systemd -------------------------------------------------------------------------------------


def build_systemctl_status(args: list[Token], ctx: Context) -> Plan:
    """``systemctl status UNIT``."""
    if len(args) != 1:
        raise Refused('usage: systemctl status UNIT')
    argv = (binary(ctx, 'systemctl'), 'status', '--no-pager', '--lines=20', '--', unit(args[0], ctx.policy))
    return Plan('systemctl-status', argv, redact=True)


def build_systemctl_timers(args: list[Token], ctx: Context) -> Plan:
    """``systemctl list-timers``."""
    no_more(args)
    return Plan('systemctl-timers', (binary(ctx, 'systemctl'), 'list-timers', '--all', '--no-pager'))


def build_journalctl(args: list[Token], ctx: Context) -> Plan:
    """``journalctl -u UNIT [-n N<=500] [--since D]``; the output is masked."""
    name, lines, since = None, '200', None
    while args:
        flag = plain(args.pop(0), 'journalctl option')
        if not args:
            raise Refused(f'{flag} needs a value')
        if flag == '-u':
            name = unit(args.pop(0), ctx.policy)
        elif flag == '-n':
            lines = number(args.pop(0), '-n', 500)
        elif flag == '--since':
            amount, letter = duration(args.pop(0))
            since = f'-{amount}{_JOURNAL_UNITS[letter]}'
        else:
            raise Refused(f'journalctl option {flag} is not allowed (only -u, -n, --since)')
    if not name:
        raise Refused('usage: journalctl -u UNIT [-n N] [--since D]')
    argv = [binary(ctx, 'journalctl'), '--no-pager', '-u', name, '-n', lines]
    if since:
        argv.append(f'--since={since}')
    return Plan('journalctl', tuple(argv), privileged=True, redact=True)


# --- ZFS -----------------------------------------------------------------------------------------


def build_zfs_list(args: list[Token], ctx: Context) -> Plan:
    """``zfs list [-t snapshot] [DATASET]``, with fixed columns."""
    snapshots = False
    if len(args) >= 2 and plain(args[0], 'zfs option') == '-t' and plain(args[1], '-t') == 'snapshot':
        snapshots = True
        args = args[2:]
    if len(args) > 1:
        raise Refused('usage: zfs list [-t snapshot] [DATASET]')
    columns = 'name,used,refer,creation' if snapshots else 'name,used,avail,refer,mountpoint'
    argv = [binary(ctx, 'zfs'), 'list', '-H', '-p', '-o', columns]
    if snapshots:
        argv += ['-t', 'snapshot']
    if args:
        argv += ['-r', dataset(args[0], ctx.policy)]
    elif ctx.policy.datasets:
        argv += ['-r', *ctx.policy.datasets]
    return Plan('zfs-list', tuple(argv), timeout=SLOW_TIMEOUT)


def build_zfs_get(args: list[Token], ctx: Context) -> Plan:
    """``zfs get PROP DATASET``, the property from a fixed list."""
    if len(args) != 2:
        raise Refused('usage: zfs get PROPERTY DATASET')
    prop = plain(args[0], 'property')
    allowed = ctx.policy.zfs_properties or DEFAULT_ZFS_PROPERTIES
    if prop not in allowed:
        raise Refused(f'property {prop} is not on the list: {", ".join(sorted(allowed))}')
    return Plan('zfs-get', (binary(ctx, 'zfs'), 'get', '-H', '-p', prop, dataset(args[1], ctx.policy)))


def build_zpool_status(args: list[Token], ctx: Context) -> Plan:
    """``zpool status [-x]``."""
    flags = [plain(a, 'option') for a in args]
    if flags not in ([], ['-x']):
        raise Refused('usage: zpool status [-x]')
    return Plan('zpool-status', (binary(ctx, 'zpool'), 'status', *flags))


def build_zpool_list(args: list[Token], ctx: Context) -> Plan:
    """``zpool list``."""
    no_more(args)
    return Plan('zpool-list', (binary(ctx, 'zpool'), 'list', '-H', '-o', 'name,size,alloc,free,cap,health'))


# --- Proxmox -------------------------------------------------------------------------------------


def build_pct_list(args: list[Token], ctx: Context) -> Plan:
    """``pct list``."""
    no_more(args)
    return Plan('pct-list', (binary(ctx, 'pct'), 'list'), privileged=True)


def build_qm_list(args: list[Token], ctx: Context) -> Plan:
    """``qm list``."""
    no_more(args)
    return Plan('qm-list', (binary(ctx, 'qm'), 'list'), privileged=True)


def build_pvesm_status(args: list[Token], ctx: Context) -> Plan:
    """``pvesm status``."""
    no_more(args)
    return Plan('pvesm-status', (binary(ctx, 'pvesm'), 'status'), privileged=True)


def _build_config(tool: str, args: list[Token], ctx: Context) -> Plan:
    if len(args) != 1:
        raise Refused(f'usage: {tool} config ID')
    argv = (binary(ctx, tool), 'config', ctid(args[0], ctx.policy))
    return Plan(f'{tool}-config', argv, privileged=True, redact=True, drop_prefixes=CONFIG_SECRET_PREFIXES)


def build_pct_config(args: list[Token], ctx: Context) -> Plan:
    """``pct config ID`` without the description, password and key lines."""
    return _build_config('pct', args, ctx)


def build_qm_config(args: list[Token], ctx: Context) -> Plan:
    """``qm config ID`` without the description, password and key lines."""
    return _build_config('qm', args, ctx)


def build_vzdump_log(args: list[Token], ctx: Context) -> Plan:
    """``vzdump-log FILE``: the last 200 lines of one file in /var/log/vzdump/."""
    if len(args) != 1 or not _VZDUMP_FILE.match(plain(args[0], 'file name')):
        raise Refused('usage: vzdump-log FILE.log, a file name in /var/log/vzdump')
    argv = (binary(ctx, 'tail'), '-n', '200', '--', f'{VZDUMP_LOG_DIR}/{args[0].text}')
    return Plan('vzdump-log', argv, privileged=True, redact=True)


def build_pct_exec(args: list[Token], ctx: Context) -> Plan:
    """``pct exec ID -- COMMAND``: run the container's own muma-ro with COMMAND.

    The node checks the id and the characters of COMMAND; the container's policy decides the rest.
    """
    if len(args) < 3 or args[1].text != '--' or args[1].quoted:
        raise Refused('usage: pct exec ID -- COMMAND')
    number_ = ctid(args[0], ctx.policy)
    _, sep, inner = ctx.command.partition(' -- ')
    if not sep or not inner.strip():
        raise Refused('usage: pct exec ID -- COMMAND')
    check_characters(inner)
    argv = (binary(ctx, 'pct'), 'exec', number_, '--', MUMA_RO, '--key', f'relay-{ctx.key}', '--command', inner)
    return Plan('pct-exec', argv, timeout=SLOW_TIMEOUT, privileged=True)


# --- help ----------------------------------------------------------------------------------------

USAGE = {
    'ls': 'ls [-l] [-a] PATH',
    'stat': 'stat PATH',
    'find': 'find PATH [-maxdepth N<=3] [-type f|d] [-name GLOB]',
    'head': 'head [-n N<=200] PATH',
    'du': 'du -s PATH',
    'df': 'df [-h] [PATH]',
    'free': 'free -m',
    'uptime': 'uptime',
    'docker-ps': 'docker ps [-a]',
    'docker-logs': 'docker logs [--tail N<=2000] [--since D] CONTAINER',
    'docker-inspect': 'docker inspect CONTAINER',
    'docker-stats': 'docker stats',
    'docker-system-df': 'docker system df',
    'docker-printenv': 'docker exec CONTAINER printenv KEY',
    'systemctl-status': 'systemctl status UNIT',
    'systemctl-timers': 'systemctl list-timers',
    'journalctl': 'journalctl -u UNIT [-n N<=500] [--since D]',
    'zfs-list': 'zfs list [-t snapshot] [DATASET]',
    'zfs-get': 'zfs get PROPERTY DATASET',
    'zpool-status': 'zpool status [-x]',
    'zpool-list': 'zpool list',
    'getfacl': 'getfacl PATH',
    'pct-list': 'pct list',
    'qm-list': 'qm list',
    'pvesm-status': 'pvesm status',
    'pct-config': 'pct config ID',
    'qm-config': 'qm config ID',
    'vzdump-log': 'vzdump-log FILE.log',
    'pct-exec': 'pct exec ID -- COMMAND',
    'help': 'help',
}


def build_help(args: list[Token], ctx: Context) -> Plan:
    """``help``: the host's verbs, roots and lists."""
    no_more(args)
    policy = ctx.policy
    lines = [f'muma-ro on a {policy.host_class} host. Quote a path with single quotes.', '', 'Verbs:']
    lines += [f'  {USAGE[v]}' for v in VERB_NAMES if v in policy.verbs]
    lines += ['', 'Roots:'] + [f'  {r.path} ({r.mode})' for r in policy.roots]
    for title, values in (
        ('Containers', sorted(policy.containers) + [p.pattern for p in policy.container_patterns]),
        ('Env keys', sorted(policy.env_keys)),
        ('Units', sorted(policy.units)),
        ('Datasets', list(policy.datasets)),
        ('Ids', sorted(policy.ctids)),
        ('head reads', list(policy.head_extensions)),
    ):
        if values:
            lines += ['', f'{title}: {", ".join(values)}']
    return Plan('help', (), text='\n'.join(lines) + '\n')


VERBS: dict[str, Builder] = {
    'help': build_help,
    'ls': build_ls,
    'stat': build_stat,
    'find': build_find,
    'head': build_head,
    'du': build_du,
    'df': build_df,
    'free': build_free,
    'uptime': build_uptime,
    'docker-ps': build_docker_ps,
    'docker-logs': build_docker_logs,
    'docker-inspect': build_docker_inspect,
    'docker-stats': build_docker_stats,
    'docker-system-df': build_docker_system_df,
    'docker-printenv': build_docker_printenv,
    'systemctl-status': build_systemctl_status,
    'systemctl-timers': build_systemctl_timers,
    'journalctl': build_journalctl,
    'zfs-list': build_zfs_list,
    'zfs-get': build_zfs_get,
    'zpool-status': build_zpool_status,
    'zpool-list': build_zpool_list,
    'getfacl': build_getfacl,
    'pct-list': build_pct_list,
    'qm-list': build_qm_list,
    'pvesm-status': build_pvesm_status,
    'pct-config': build_pct_config,
    'qm-config': build_qm_config,
    'vzdump-log': build_vzdump_log,
    'pct-exec': build_pct_exec,
}

# Words that are a tool, not a verb: the verb is the tool plus its sub-command.
_SUB = {
    ('docker', 'ps'): 'docker-ps',
    ('docker', 'logs'): 'docker-logs',
    ('docker', 'inspect'): 'docker-inspect',
    ('docker', 'stats'): 'docker-stats',
    ('docker', 'exec'): 'docker-printenv',
    ('systemctl', 'status'): 'systemctl-status',
    ('systemctl', 'list-timers'): 'systemctl-timers',
    ('zfs', 'list'): 'zfs-list',
    ('zfs', 'get'): 'zfs-get',
    ('zpool', 'status'): 'zpool-status',
    ('zpool', 'list'): 'zpool-list',
    ('pct', 'list'): 'pct-list',
    ('pct', 'config'): 'pct-config',
    ('pct', 'exec'): 'pct-exec',
    ('qm', 'list'): 'qm-list',
    ('qm', 'config'): 'qm-config',
    ('pvesm', 'status'): 'pvesm-status',
}


# Verbs that are one word on the command line.
_SINGLE = frozenset(VERBS) - frozenset(_SUB.values()) - {'docker-system-df'}


def verb_of(tokens: list[Token]) -> tuple[str, list[Token]]:
    """Name the verb and return its arguments. Refuses a word that is no verb."""
    words = [t.text if not t.quoted else '' for t in tokens[:3]]
    if words[:3] == ['docker', 'system', 'df']:
        return 'docker-system-df', tokens[3:]
    if len(words) >= 2 and (words[0], words[1]) in _SUB:
        return _SUB[(words[0], words[1])], tokens[2:]
    if words[0] in _SINGLE:
        return words[0], tokens[1:]
    shown = ' '.join(w for w in words[:2] if w)
    raise Refused(f'{shown or "that"} is not a muma-ro verb; run help')


def build(tokens: list[Token], ctx: Context) -> Plan:
    """Steps 4 to 6: find the verb, check that the host enables it, and build its argument list."""
    verb, args = verb_of(tokens)
    if verb not in ctx.policy.verbs:
        raise Refused(f'{verb} is not enabled on this host; run help')
    return VERBS[verb](list(args), ctx)
