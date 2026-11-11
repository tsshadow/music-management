"""Every ${VAR} without a default in docker/docker-compose.yml has a line in .env.example.

A missing one renders as an empty string with only a warning, so a new host got the image
`muma/:latest` and workers without a music-manager address (issue #210). Commented-out lines are
skipped; their variables are not used.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / 'docker' / 'docker-compose.yml'
ENV_EXAMPLE = ROOT / '.env.example'

_IMAGE_LINE = re.compile(r'^\s*image:\s*(.+)$')
_VARIABLE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)')


def _image_variables():
    """Return the variable names used in the active image: lines of the main compose file."""
    names = set()
    for line in COMPOSE.read_text(encoding='utf-8').splitlines():
        match = _IMAGE_LINE.match(line)
        if match:
            names.update(_VARIABLE.findall(match.group(1)))
    return names


def _env_example_keys():
    """Return the keys .env.example defines, set or empty (commented lines do not count)."""
    keys = set()
    for line in ENV_EXAMPLE.read_text(encoding='utf-8').splitlines():
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
        if match:
            keys.add(match.group(1))
    return keys


def test_compose_has_image_variables():
    """The scan finds the variables it is meant to guard."""
    assert {'DOCKER_USER', 'IMAGE_CORE'} <= _image_variables()


def test_every_image_variable_is_in_env_example():
    """An image variable without an .env.example entry renders as an empty image name."""
    # IMAGE_TAG and SCHEMA_IMAGE_TAG carry an in-line default (:-latest) and deploy.sh sets them.
    optional = {'IMAGE_TAG', 'SCHEMA_IMAGE_TAG'}
    missing = sorted(_image_variables() - _env_example_keys() - optional)
    assert not missing, f'.env.example lacks {missing}: compose renders an empty image name'


def _variables_without_default():
    """Return the variables the active lines of the main compose file use without a default."""
    names = set()
    for line in COMPOSE.read_text(encoding='utf-8').splitlines():
        if line.lstrip().startswith('#'):
            continue
        for match in re.finditer(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(:?[-?])?', line):
            if not match.group(2):
                names.add(match.group(1))
    return names


def test_every_variable_without_a_default_is_in_env_example():
    """`docker compose config` with a copied .env.example warns about no unset variable."""
    missing = sorted(_variables_without_default() - _env_example_keys())
    assert not missing, f'.env.example lacks {missing}: compose renders them empty'
