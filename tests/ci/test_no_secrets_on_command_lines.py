"""No password, token or key on a command line (GitLab #40, bug report 038).

A command line is not private. `ps` and `/proc/<pid>/cmdline` show it to every account on the
machine -- on the shared shell-executor runner that is every pipeline, on the production host
every local account -- and a process inside a container is just as visible from the host. An
interactive command also lands in shell history and a CI command in the job log when `set -x` is
on. Bug report 038 moved the deploy off this; this guard keeps every other shell script, compose
file and CI definition from sliding back.

The accepted ways to hand a secret over:

- MariaDB clients: `MYSQL_PWD` in the environment (or a 0600 `--defaults-extra-file`), never
  `-p<pw>` / `--password=<pw>`.
- `docker run` / `docker exec`: export the value and pass `-e NAME` *without* `=value`; docker
  copies it from its own environment.
- curl: the header through a process substitution (`-H @<(printf 'X-API-Key: %s\\n' "$KEY")`) or a
  config on stdin (`-K -`), a body through `--data-binary @-`; never `-H "X-API-Key: $KEY"` or
  `-u user:$PASS`.
- sshpass: `SSHPASS=... sshpass -e`, never `sshpass -p`.
- values for a remote shell: on ssh's stdin, never in the remote command string.

A line that must stay -- throwaway credentials of a disposable test container, say -- goes in
ALLOWLIST with the reason. An entry that no longer matches anything fails the build as well, so the
list cannot outlive the lines it excuses.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# What is scanned: everything that runs as a shell command line.
SCANNED_SUFFIXES = ('.sh', '.bash', '.yml', '.yaml', '.gradle', '.gradle.kts')
SCANNED_NAMES = ('Dockerfile', '.gitlab-ci.yml')
# Test code builds these shapes on purpose to assert against them; vendored/upstream trees and
# docs are not command lines.
EXCLUDED_PREFIXES = (
    'tests/',
    'services/music-management-server/src/',
    'services/frontend/node_modules/',
    'docs/',
)

SECRET_NAME = r'[A-Z0-9_]*(?:PASS|PASSWORD|PWD|SECRET|TOKEN|API_KEY|APIKEY)[A-Z0-9_]*'
SECRET_HEADER = r'(?:PRIVATE-TOKEN|JOB-TOKEN|X-API-Key|X-Upload-Password|Authorization|Cookie)'

PATTERNS = {
    'mariadb/mysql -p<password>': re.compile(
        r'\b(?:mysql|mariadb|mysqldump|mariadb-dump|mysqladmin|mariadb-admin|mariadb-upgrade|mysql_upgrade)'
        r'\b[^|;&\n]*\s-p(?![\s\'"]*$)(?!\s)'
    ),
    '--password=<value> / --password <value>': re.compile(r'--password(?:=|\s+)(?!-stdin)[^\s\\]'),
    'sshpass -p': re.compile(r'\bsshpass\s+(?:-\w+\s+)*-p\b'),
    'docker -e NAME=<secret>': re.compile(rf'(?:^|[\s(])(?:-e|--env)\s+["\']?{SECRET_NAME}=\S'),
    'docker --build-arg NAME=<secret>': re.compile(rf'--build-arg\s+["\']?{SECRET_NAME}=\S'),
    'curl header with an inline secret': re.compile(
        rf'(?:\s-H|--header)\s+["\']?{SECRET_HEADER}:\s*(?!<)[^\s"\']', re.IGNORECASE
    ),
    'curl -u user:password': re.compile(r'\bcurl\b[^|;\n]*\s(?:-u|--user)\s+["\']?[^\s"\']*:\S'),
    'keytool -storepass/-keypass <value>': re.compile(r'["\']?-(?:store|key|src|dest)(?:store)?pass["\']?(?!:)[\s,]'),
    'secret assigned in a remote command string': re.compile(rf'\bssh\b[^|;\n]*["\']{SECRET_NAME}=["\']?\$'),
}

# (path, pattern name, substring of the line, reason). Keep the substring specific enough that a
# new, real secret on the same file does not ride along.
ALLOWLIST = [
    # Disposable test containers: fixed, published throwaway credentials, no real secret exists.
    (
        'scripts/lib/e2e-stack.sh',
        'mariadb/mysql -p<password>',
        '-ptest-root-password',
        'root password of the throwaway e2e MariaDB, also in docker/compose.test.yml',
    ),
    (
        'scripts/test/db-integration.sh',
        'mariadb/mysql -p<password>',
        '-ptest-root-password',
        'root password of the throwaway integration MariaDB',
    ),
    (
        'scripts/test/db-integration.sh',
        'docker -e NAME=<secret>',
        'MYSQL_ROOT_PASSWORD=test-root-password',
        'root password of the throwaway integration MariaDB',
    ),
    (
        'scripts/test/db-integration.sh',
        'docker -e NAME=<secret>',
        'MYSQL_PASSWORD="$DB_PASS"',
        'app password of the throwaway integration MariaDB, a fixed test value',
    ),
    *[
        (
            path,
            'docker -e NAME=<secret>',
            value,
            'placeholder signing config: Gradle needs the variables set, unit/lint builds sign nothing',
        )
        for path in (
            'scripts/test/android-unit.sh',
            'scripts/test/muma-mobile-detekt.sh',
            'scripts/test/muma-mobile-ktlint.sh',
            'scripts/test/muma-mobile-lint.sh',
            'scripts/test/muma-mobile-unit.sh',
        )
        for value in ('SIGNING_STORE_PASSWORD=dummy', 'SIGNING_KEY_PASSWORD=dummy')
    ],
    *[
        (
            'scripts/test/muma-mobile-emulator-smoke.sh',
            'docker -e NAME=<secret>',
            value,
            'placeholder signing config for the emulator smoke build',
        )
        for value in ('SIGNING_STORE_PASSWORD=dummy-ci-password', 'SIGNING_KEY_PASSWORD=dummy-ci-password')
    ],
]


def _tracked_files():
    out = subprocess.run(
        ['git', 'ls-files'], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    for rel in out:
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        name = rel.rsplit('/', 1)[-1]
        if rel.endswith(SCANNED_SUFFIXES) or name in SCANNED_NAMES or name.startswith('Dockerfile'):
            path = REPO_ROOT / rel
            if path.is_file():
                yield rel, path


def scan_line(line):
    """Return the names of every pattern the line matches. Comment lines are skipped."""
    if line.lstrip().startswith('#'):
        return []
    return [name for name, pattern in PATTERNS.items() if pattern.search(line)]


def _allowed(rel, name, line, used):
    for index, (path, pattern_name, needle, _reason) in enumerate(ALLOWLIST):
        if path == rel and pattern_name == name and (needle is None or needle in line):
            used.add(index)
            return True
    return False


def _findings():
    findings, used = [], set()
    for rel, path in _tracked_files():
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for name in scan_line(line):
                if not _allowed(rel, name, line, used):
                    findings.append(f'{rel}:{number}: {name}: {line.strip()}')
    return findings, used


def test_no_secret_on_a_command_line():
    findings, _ = _findings()
    assert findings == [], (
        'a secret is passed on a command line, visible in ps and /proc/<pid>/cmdline; see this '
        "test's docstring for the accepted alternatives:\n" + '\n'.join(findings)
    )


def test_every_allowlist_entry_still_matches():
    _, used = _findings()
    stale = [ALLOWLIST[i][:3] for i in range(len(ALLOWLIST)) if i not in used]
    assert stale == [], f'allowlist entries that no longer match any line, remove them: {stale}'


@pytest.mark.parametrize(
    'line',
    [
        'docker exec -i "$c" mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" music',
        "ssh h \"docker exec db sh -c 'exec mariadb-dump -uroot -p\\\"\\$MYSQL_ROOT_PASSWORD\\\" db'\"",
        'mysqldump -u root --password="$PW" db',
        'mysql --password secret db',
        'sshpass -p "${pass}" ssh host',
        '    -e SIGNING_KEY_PASSWORD="${SIGNING_KEY_PASSWORD}" \\',
        'docker exec -e MYSQL_PWD="$ROOT_PASS" db mariadb',
        '    GITHUB_ENV=(-e "GITHUB_COM_TOKEN=${RENOVATE_GITHUB_COM_TOKEN}")',
        'docker build --build-arg NPM_TOKEN=$NPM_TOKEN .',
        'curl -sf --header "PRIVATE-TOKEN: ${TAG_CREATION_TOKEN}" "$API"',
        'curl -H "X-API-Key: $MUMA_SYSTEM_API_KEY" "$URL"',
        "curl -H 'Authorization: Bearer '\"$T\" x",
        'curl -u "admin:$PASS" https://x',
        "ssh root@h \"RO_PASS='${RO_PASS}'\" 'bash -s'",
        '                    "-storepass", storePass,',
        'keytool -genkeypair -keystore k.jks -keypass "$P" -alias a',
    ],
)
def test_scanner_flags(line):
    assert scan_line(line), line


@pytest.mark.parametrize(
    'line',
    [
        'MYSQL_PWD="$DB_PASS" docker exec -e MYSQL_PWD "$DB_CONTAINER" mysql -u"$DB_USER" db',
        "docker exec -i \"$c\" sh -c 'MYSQL_PWD=\"$MARIADB_ROOT_PASSWORD\" exec mariadb -uroot -N'",
        'python3 tools/db_backup.py --password-stdin --exec run_remote_sql',
        'SSHPASS="${pass}" sshpass -e ssh host',
        '    -e SIGNING_KEY_PASSWORD \\',
        "curl -sf --header @<(printf 'PRIVATE-TOKEN: %s\\n' \"$TAG_CREATION_TOKEN\") \"$API\"",
        "confirm 'x' \"curl -X POST $URL -H 'X-API-Key: <admin>'\"",
        'curl -H "Content-Type: application/json" -d @- "$URL"',
        '# mariadb -uroot -p"$PW" -- a comment explaining what not to do',
        'python -m pytest -p no:warnings tests/',
        '                    "-storepass:env", "MUMA_KEYTOOL_STORE_PASS",',
        'printf \'%s\' "$DOCKERHUB_TOKEN" | docker login --username "$U" --password-stdin',
    ],
)
def test_scanner_passes(line):
    assert scan_line(line) == [], line


# --- The .env reader ------------------------------------------------------------------------------
# GitLab #40 also named the other half of bug report 038's item 8: about ten scripts still read .env
# with a `sed 's/[[:space:]]*#.*$//'` loop, which cuts a password such as `ab#cd` down to `ab` while
# docker-compose, reading the same file, sees all of it. scripts/lib/dotenv.sh reads it compose's
# way; nothing else may carry the old loop.
ENV_LOOP = re.compile(r'clean_line=.*sed .s/\[\[:space:\]\]\*#')


def test_no_script_cuts_env_values_at_a_hash():
    offenders = []
    for rel, path in _tracked_files():
        if not rel.endswith('.sh'):
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if ENV_LOOP.search(line):
                offenders.append(f'{rel}:{number}')
    assert offenders == [], f'.env read with the #-cutting sed loop, use dotenv_load: {offenders}'


def test_dotenv_load_keeps_a_hash_inside_a_value(tmp_path):
    env = tmp_path / '.env'
    env.write_text('MYSQL_ROOT_PASSWORD=ab#cd\nQUOTED="x # y"\nWITH_COMMENT=v # note\n', encoding='utf-8')
    script = (
        f'. "{REPO_ROOT}/scripts/lib/dotenv.sh"; dotenv_load "{env}"; '
        'printf "%s|%s|%s" "$MYSQL_ROOT_PASSWORD" "$QUOTED" "$WITH_COMMENT"'
    )
    out = subprocess.run(['bash', '-c', script], check=True, capture_output=True, text=True).stdout
    assert out == 'ab#cd|x # y|v'
