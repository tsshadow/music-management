"""LMS's managed-portrait folder is music-manager's portrait folder, seen through LMS's mount.

LMS keeps an artist's preferred artwork when it points at an image under
`LMS_ARTIST_IMAGE_MANAGED_DIRECTORY` (bug report 139). music-manager stores those
portraits under its own `STORAGE_PATH`, through its own mount of the same share. The two
live in different compose files (the LMS stack is deployed on its own), so nothing but this
test notices when one moves and the other does not -- and the symptom, portraits flipping
back to release covers on every scan, would look like bug report 139 all over again.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MUMA_COMPOSE = ROOT / 'docker' / 'docker-compose.yml'
LMS_COMPOSE = ROOT / 'services' / 'music-management-server' / 'docker-compose.yml'
TEST_COMPOSE = ROOT / 'docker' / 'compose.test.yml'

# The container paths each side mounts the music share at; library_paths.py's defaults.
MUMA_MUSIC_ROOT = '/mnt/music'
LMS_MUSIC_ROOT = '/music'


def _service(path: Path, name: str) -> dict:
    """One service of a compose file, anchors resolved."""
    return yaml.safe_load(path.read_text(encoding='utf-8'))['services'][name]


def _targets(service: dict) -> set[str]:
    """The container side of every bind mount of `service`."""
    targets = set()
    for volume in service.get('volumes', []):
        if not isinstance(volume, str) or ':' not in volume:
            continue
        # The source may hold `${VAR:-default}`, so count from the end: target[:mode].
        parts = volume.split(':')
        targets.add(parts[-2] if parts[-1] in ('ro', 'rw') else parts[-1])
    return targets


def _environment(service: dict) -> dict[str, str]:
    """A service's environment as a dict, whether written as a list or a mapping."""
    env = service.get('environment', {})
    if isinstance(env, list):
        return dict(item.split('=', 1) for item in env)
    return {key: str(value) for key, value in env.items()}


def _default(value: str) -> str:
    """`${NAME:-default}` -> default; a plain value is returned as it is."""
    match = re.fullmatch(r'\$\{[A-Z_]+:-([^}]*)\}', value)
    return match.group(1) if match else value


def _expected_lms_directory() -> str:
    manager = _service(MUMA_COMPOSE, 'music-manager')
    storage_path = _environment(manager)['STORAGE_PATH']
    assert MUMA_MUSIC_ROOT in _targets(manager)
    assert storage_path.startswith(MUMA_MUSIC_ROOT + '/'), storage_path
    return LMS_MUSIC_ROOT + storage_path[len(MUMA_MUSIC_ROOT) :]


def test_the_lms_stack_points_at_music_managers_portrait_folder():
    lms = _service(LMS_COMPOSE, 'lms')
    assert LMS_MUSIC_ROOT in _targets(lms)
    configured = _default(_environment(lms)['LMS_ARTIST_IMAGE_MANAGED_DIRECTORY'])
    assert configured == _expected_lms_directory() == '/music/artists'


def test_the_test_stack_uses_the_same_folder():
    server = _service(TEST_COMPOSE, 'music-management-server')
    assert _environment(server)['LMS_ARTIST_IMAGE_MANAGED_DIRECTORY'] == _expected_lms_directory()
