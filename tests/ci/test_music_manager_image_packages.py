"""Every services.* package the music-manager code imports is copied into its image.

The music-manager image copies a hand-picked set of packages under services/. On 2026-09-25
services/tagger/todo_label_repair.py imported services.importer, which the image did not
contain, and the admin endpoint answered 500 with ModuleNotFoundError in production while
every test passed (the test runner has the whole tree). Bug report 092.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / 'docker' / 'Dockerfile.music-manager'
#: The packages whose code runs inside the music-manager container.
RUNTIME_PACKAGES = ('music_manager', 'tagger', 'scanner', 'common', 'downloader')


def copied_packages() -> set[str]:
    """The services/<name>/ directories the Dockerfile copies."""
    text = DOCKERFILE.read_text(encoding='utf-8')
    return set(re.findall(r'^COPY services/([A-Za-z0-9_]+)/ ', text, flags=re.MULTILINE))


def imported_packages() -> dict[str, set[str]]:
    """services.<name> packages imported by non-test modules of the runtime packages."""
    found: dict[str, set[str]] = {}
    for package in RUNTIME_PACKAGES:
        for path in (ROOT / 'services' / package).rglob('*.py'):
            name = path.name
            if name.startswith('test_') or name.endswith('Test.py') or '/tests/' in path.as_posix():
                continue
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                elif isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                for module in modules:
                    parts = module.split('.')
                    if len(parts) >= 2 and parts[0] == 'services':
                        found.setdefault(parts[1], set()).add(str(path.relative_to(ROOT)))
    return found


def test_every_imported_services_package_is_copied_into_the_image():
    copied = copied_packages()
    missing = {pkg: sorted(files)[:3] for pkg, files in imported_packages().items() if pkg not in copied}
    assert not missing, f'music-manager image lacks packages its code imports: {missing}'
