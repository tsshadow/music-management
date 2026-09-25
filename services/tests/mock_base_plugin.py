"""pytest plugin behind ``@pytest.mark.mock_base``: stubs per test module, never session-wide.

Registered from the root ``conftest.py``. A test module opts in with a module-level

    pytestmark = pytest.mark.mock_base('mutagen', 'Cache')

(the names are the keys of ``mock_base.STUB_BUILDERS``). The marker is read from the
file's source with ``ast`` before the module is imported, because most stubs have to be
in ``sys.modules`` while the module's own imports run. That is also why the marker has
to be module-level, with literal string arguments; putting it on a class or function is
rejected at collection time.

How the isolation works. Every distinct set of stub names is a *world*. Switching into a
world snapshots ``sys.modules``, lifts out every project module (anything under the
repository root) and every real module a stub replaces, and installs the world's stubs --
or, from the second time on, everything the world imported before. Switching out puts the
snapshot back: whatever the world imported of the project, the stubs themselves, and any
module a test module put into ``sys.modules`` by hand go back into the world's own store,
not into the session. Third-party modules imported for the first time inside a world are
real, and stay (re-importing them would cost time and some C extensions cannot be loaded
twice).

The switch happens around the collection of each test file and around each test, and
only when the next file needs a different world, so a run of consecutive files that ask
for the same stubs switches once. Modules that ask for the same set share their world,
the way every test used to share the one session-wide set of stubs.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from services.tests import mock_base

ROOT = Path(__file__).resolve().parents[2]
_ROOT_PREFIX = str(ROOT) + os.sep
_MARKER = 'mock_base'

# Never lifted out of sys.modules: the plugin and the stub library themselves with their
# parent packages, and pytest's conftest modules, which pytest holds on to and which must
# not be re-imported under a world.
_RETAINED_PACKAGES = ('services', 'services.tests')
_KEEP = {'services.tests.mock_base', 'services.tests.mock_base_plugin', *_RETAINED_PACKAGES}


def _kept(name: str) -> bool:
    """True for sys.modules keys the plugin must never move between worlds."""
    return name in _KEEP or name == 'conftest' or name.endswith('.conftest')


def _under_root(path) -> bool:
    """True for a file inside this repository that is not an installed package."""
    if not path:
        return False
    path = str(path)
    if not path.startswith(_ROOT_PREFIX):
        path = os.path.realpath(path)
        if not path.startswith(_ROOT_PREFIX):
            return False
    return os.sep + 'site-packages' + os.sep not in path and os.sep + 'dist-packages' + os.sep not in path


def _is_project(module) -> bool:
    """True for a module whose source lives in this repository (services/, tools/, tests/)."""
    if mock_base.is_stub(module):
        return False
    file = getattr(module, '__file__', None)
    if file:
        return _under_root(file)
    locations = getattr(getattr(module, '__spec__', None), 'submodule_search_locations', None) or []
    return any(_under_root(location) for location in locations)


def _is_real_external(module) -> bool:
    """True for a genuinely imported module from outside the repository.

    Such a module is left in sys.modules when a world is switched out. Everything else a
    world added -- stubs, fakes a test registered by hand (no spec), project modules --
    belongs to that world.
    """
    if mock_base.is_stub(module):
        return False
    spec = getattr(module, '__spec__', None)
    if spec is None:
        return False
    if spec.origin in ('built-in', 'frozen'):
        return True
    file = getattr(module, '__file__', None) or spec.origin
    if file:
        return not _under_root(file)
    locations = spec.submodule_search_locations or []
    return bool(locations) and not any(_under_root(location) for location in locations)


class _World:
    """One set of stub names and everything imported under it."""

    def __init__(self, names: frozenset):
        self.names = names
        self.modules: dict | None = None


class WorldManager:
    """Moves sys.modules between the clean session and the worlds of stubbed test modules."""

    def __init__(self):
        self.current: _World | None = None
        self._worlds: dict[frozenset, _World] = {}
        self._clean: dict = {}

    def switch(self, names) -> None:
        """Make the world for these stub names current (the clean session for no names)."""
        names = frozenset(names)
        if (self.current.names if self.current else frozenset()) == names:
            return
        if self.current is not None:
            self._leave()
        if names:
            self._enter(self._worlds.setdefault(names, _World(names)))

    def _enter(self, world: _World) -> None:
        """Snapshot the clean session and install the world's modules in its place."""
        self._clean = dict(sys.modules)
        for name, module in self._clean.items():
            if _kept(name):
                continue
            if _is_project(module) or mock_base.owned_by_stub(name, world.names):
                del sys.modules[name]
        self.current = world
        if world.modules is None:
            mock_base.build_stubs(world.names)
        else:
            sys.modules.update(world.modules)
        _fix_retained_packages()

    def _leave(self) -> None:
        """Store what the current world imported and put the clean session back."""
        world = self.current
        assert world is not None
        clean = self._clean
        captured = {}
        for name, module in list(sys.modules.items()):
            if clean.get(name) is module or _kept(name):
                continue
            if (
                name in clean
                or _is_project(module)
                or mock_base.owned_by_stub(name, world.names)
                or not _is_real_external(module)
            ):
                captured[name] = module
        world.modules = captured
        for name in list(sys.modules):
            if name in captured:
                del sys.modules[name]
        for name, module in clean.items():
            if sys.modules.get(name) is not module:
                sys.modules[name] = module
        self.current = None
        self._clean = {}
        _fix_retained_packages()


def _retained_packages() -> list:
    """The project packages that stay in sys.modules across worlds."""
    return [sys.modules[name] for name in _RETAINED_PACKAGES if name in sys.modules]


def _fix_retained_packages() -> None:
    """Point a retained package's submodule attributes at the current world's submodules.

    Importing ``services.common`` sets ``services.common`` as an attribute of the
    ``services`` package, which stays across worlds. Left alone, ``mock.patch`` (which
    walks attributes) would reach a module of the world that set it last.
    """
    for package in _retained_packages():
        prefix = package.__name__ + '.'
        for attr, value in list(vars(package).items()):
            if getattr(value, '__name__', None) == prefix + attr and type(value).__name__ in ('module', 'MagicMock'):
                current = sys.modules.get(prefix + attr)
                if current is None:
                    delattr(package, attr)
                elif current is not value:
                    setattr(package, attr, current)
        for name, module in list(sys.modules.items()):
            if name.startswith(prefix) and '.' not in name[len(prefix) :]:
                setattr(package, name[len(prefix) :], module)


MANAGER = WorldManager()
_DECLARED: dict[Path, frozenset] = {}


def _dotted(node) -> str:
    """Render an ast.Attribute / ast.Name chain as a dotted name ('' for anything else)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f'{base}.{node.attr}' if base else ''
    return ''


def declared_stubs(path: Path) -> frozenset:
    """The stub names a test file's module-level ``pytestmark`` asks for, read from its source."""
    if path in _DECLARED:
        return _DECLARED[path]
    names: set = set()
    if path.suffix == '.py' and path.is_file():
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, 'target', None)]
            if not any(isinstance(t, ast.Name) and t.id == 'pytestmark' for t in targets):
                continue
            for call in ast.walk(node.value):
                if not (isinstance(call, ast.Call) and _dotted(call.func).endswith('mark.' + _MARKER)):
                    continue
                for arg in call.args:
                    if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                        raise pytest.UsageError(f'{path}: mock_base(...) takes literal stub names only')
                    names.add(arg.value)
        unknown = sorted(names - set(mock_base.STUB_BUILDERS))
        if unknown:
            raise pytest.UsageError(
                f'{path}: unknown mock_base stub(s) {unknown}; known: {sorted(mock_base.STUB_BUILDERS)}'
            )
    _DECLARED[path] = frozenset(names)
    return _DECLARED[path]


def _stubs_for(node) -> frozenset:
    """The stub set the file a collector or item comes from asks for."""
    path = getattr(node, 'path', None)
    if path is None or not path.is_file():
        return frozenset()
    return declared_stubs(Path(path))


def leaked_stubs() -> list[str]:
    """sys.modules keys that currently hold a mock_base stub (empty in the clean session)."""
    leaks = []
    for name, module in list(sys.modules.items()):
        if (
            module is not None
            and mock_base.owned_by_stub(name, mock_base.STUB_MODULE_NAMES)
            and mock_base.is_stub(module)
        ):
            leaks.append(name)
    return sorted(leaks)


LEAKS_AFTER_COLLECTION = pytest.StashKey[list]()


def pytest_configure(config):
    """Register the marker and set the environment defaults the code under test reads."""
    config.addinivalue_line(
        'markers',
        'mock_base(*names): module-level only -- install these services/tests/mock_base.py stubs '
        'while this module is imported and while its tests run',
    )
    mock_base.apply_env_defaults()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_make_collect_report(collector):
    """Collect (import) each test file inside the world its marker asks for."""
    MANAGER.switch(_stubs_for(collector))
    return (yield)


def pytest_collection_modifyitems(config, items):
    """Reject a mock_base marker anywhere but at module level: it could not take effect."""
    del config
    for item in items:
        asked = {name for mark in item.iter_markers(_MARKER) for name in mark.args}
        if asked != set(_stubs_for(item)):
            raise pytest.UsageError(
                f'{item.nodeid}: mock_base must be declared as a module-level '
                f"`pytestmark = pytest.mark.{_MARKER}('...')` with literal names, not on a class or test"
            )


def pytest_collection_finish(session):
    """End collection in the clean session and record whether any stub leaked into it."""
    MANAGER.switch(frozenset())
    session.config.stash[LEAKS_AFTER_COLLECTION] = leaked_stubs()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    """Run each test (setup, call and teardown) inside its module's world."""
    del nextitem
    MANAGER.switch(_stubs_for(item))
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtestloop(session):
    """Hand the session back clean once the last test has run."""
    del session
    try:
        return (yield)
    finally:
        MANAGER.switch(frozenset())
