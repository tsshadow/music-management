"""Every documented compose combination renders.

`scripts/dev.sh` layers four files, and for a long time that stack did not
render at all: `docker-compose.dev.yml` added a `music-management-server`
service that no other file defines (LMS is its own stack), and the overlays
repeated `security_opt: [no-new-privileges:true]`, which compose 2.26 -- the
workstation's version -- appends instead of merging and then rejects as
"array items must be unique" (docs/bug-reports/086-mem-limits-and-dev-overlay.md).
Nobody noticed because nothing rendered the combination; each file on its own
was fine.

Two layers:

- a static check with PyYAML that needs nothing installed: every service an
  overlay mentions is defined by an earlier file or brings its own image/build,
  and no list-valued key that compose merges by appending ends up with a
  duplicate entry;
- the real thing, `docker compose ... config -q`, when the compose v2 CLI is on
  the machine. The CI Python container has no Docker CLI, so there it skips with
  a message; on the workstation and on a developer machine it runs.

The combinations are the ones the repository documents: production
(scripts/deploy.sh), the separate LMS stack, the backup timers
(scripts/backup/systemd/), README's "entire stack", scripts/dev.sh, and the
standalone files the docs mention.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

COMBINATIONS = {
    # scripts/deploy.sh, and dev.sh's first `up -d db`.
    'production': ['docker/docker-compose.yml'],
    'lms-stack': ['services/music-management-server/docker-compose.yml'],
    # The systemd timers run this file with a single -f.
    'backup': ['docker/docker-compose.backup.yml'],
    # README "Start the entire stack".
    'base+tools': ['docker/docker-compose.yml', 'docker/docker-compose.tools.yml'],
    # scripts/dev.sh COMPOSE_FILES.
    'dev.sh': [
        'docker/docker-compose.yml',
        'docker/docker-compose.workers.yml',
        'docker/docker-compose.tools.yml',
        'docker/docker-compose.dev.yml',
    ],
    'core': ['docker/docker-compose.core.yml'],
    'full': ['docker/docker-compose.full.yml'],
    # scripts/test/core-smoke.sh and friends.
    'test-stack': ['docker/compose.test.yml'],
}

# List keys compose 2.26 concatenates across files without de-duplicating, and
# then validates as unique. Newer compose de-duplicates; the workstation does not.
APPENDED_UNIQUE_LISTS = ('security_opt', 'cap_add', 'cap_drop', 'dns')

# Enough for every ${VAR} that ends up in a volume spec or image name without a
# default; compose refuses ":/mnt/music" rather than warning about it.
DUMMY_ENV = {
    'HOST_DATA_PATH': '/tmp/muma-render/data',
    'HOST_MUSIC_PATH': '/tmp/muma-render/music',
    'DOCKER_USER': 'render',
    'IMAGE_CORE': 'core',
    'IMAGE_IMPORTER': 'importer',
    'IMAGE_DOWNLOADER': 'downloader',
    'IMAGE_TELEGRAM': 'telegram',
    'IMAGE_TOOLS': 'tools',
    'IMAGE_NAME': 'render/lms',
    'LMS_TAG': 'latest',
    'FIREFOX_PASSWORD': 'render',
}


def _load(relative: str) -> dict:
    """Parse one compose file with its YAML anchors resolved."""
    return yaml.safe_load((ROOT / relative).read_text(encoding='utf-8')) or {}


def test_every_combination_names_existing_files():
    for name, files in COMBINATIONS.items():
        for relative in files:
            assert (ROOT / relative).is_file(), f'{name}: {relative} does not exist'


def test_dev_sh_still_uses_the_combination_tested_here():
    """If dev.sh changes its file list, the list above has to follow."""
    script = (ROOT / 'scripts' / 'dev.sh').read_text(encoding='utf-8')
    expected = ' '.join(f'-f {relative}' for relative in COMBINATIONS['dev.sh'])
    assert f'COMPOSE_FILES="{expected}"' in script


@pytest.mark.parametrize('name', sorted(COMBINATIONS))
def test_every_service_has_an_image_or_build_once_merged(name):
    """An overlay can only add to a service an earlier file defines."""
    merged: dict[str, dict] = {}
    for relative in COMBINATIONS[name]:
        for service, body in (_load(relative).get('services') or {}).items():
            merged.setdefault(service, {}).update(
                {key: value for key, value in (body or {}).items() if key in ('image', 'build')}
            )
    for service, body in merged.items():
        assert body, (
            f'{name}: service {service!r} has neither an image nor a build context in any of '
            f'{COMBINATIONS[name]} -- an overlay entry for a service no file defines'
        )


@pytest.mark.parametrize('name', sorted(COMBINATIONS))
def test_appended_lists_stay_unique_once_merged(name):
    merged: dict[tuple[str, str], list] = {}
    for relative in COMBINATIONS[name]:
        for service, body in (_load(relative).get('services') or {}).items():
            for key in APPENDED_UNIQUE_LISTS:
                merged.setdefault((service, key), []).extend((body or {}).get(key) or [])
    for (service, key), values in merged.items():
        duplicates = sorted({value for value in values if values.count(value) > 1})
        assert not duplicates, (
            f'{name}: {service}.{key} repeats {duplicates} across files; compose 2.26 rejects the '
            'merged list. State it once, in the base file.'
        )


def _compose_v2() -> bool:
    """True when `docker compose` (the v2 plugin) answers."""
    if shutil.which('docker') is None:
        return False
    try:
        result = subprocess.run(['docker', 'compose', 'version'], capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@pytest.mark.parametrize('name', sorted(COMBINATIONS))
def test_combination_renders_with_compose_v2(name, tmp_path):
    if not _compose_v2():
        pytest.skip('docker compose v2 CLI not available here; the static checks above still ran')
    env_file = tmp_path / 'render.env'
    env_file.write_text(''.join(f'{key}={value}\n' for key, value in DUMMY_ENV.items()), encoding='utf-8')
    command = ['docker', 'compose', '--env-file', str(env_file)]
    for relative in COMBINATIONS[name]:
        command += ['-f', str(ROOT / relative)]
    command += ['config', '-q']
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    errors = [line for line in result.stderr.splitlines() if 'level=warning' not in line]
    assert result.returncode == 0, f'{name} does not render:\n' + '\n'.join(errors)
