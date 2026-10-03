"""Pylint plugin: turn off three import-layout checks in test modules only.

A test module imports its subject after the mock_base stubs or a sys.path
change are in place. It imports inside a test to keep a stub local, and it
names a test argument after the pytest fixture it gets. Pylint reports those as
wrong-import-position, import-outside-toplevel and redefined-outer-name. In a
test they are how the module has to be built, so this plugin disables them for
test files. Production code keeps all three.

A file is a test file when a directory in its path is named ``tests``, or its
name matches ``test_*.py``, ``*Test.py`` or ``conftest.py``. These are the
files pytest collects (pytest.ini), plus the fixture files.

.pylintrc puts this directory on sys.path in its init-hook and loads the plugin
by name, so pylint has to run from the repository root (scripts/lint.sh does).
"""

from __future__ import annotations

from pathlib import PurePath
from typing import TYPE_CHECKING

from pylint.checkers import BaseRawFileChecker

if TYPE_CHECKING:
    from astroid import nodes
    from pylint.lint import PyLinter

TEST_LAYOUT_MESSAGES = (
    'wrong-import-position',
    'import-outside-toplevel',
    'redefined-outer-name',
)


def is_test_file(path: str | None) -> bool:
    """Return True when ``path`` is a test module, by the rule in the module docstring."""
    if not path:
        return False
    pure = PurePath(path)
    name = pure.name
    if not name.endswith('.py'):
        return False
    if 'tests' in pure.parts[:-1]:
        return True
    return name.startswith('test_') or name.endswith('Test.py') or name == 'conftest.py'


class TestLayoutChecker(BaseRawFileChecker):
    """Disable TEST_LAYOUT_MESSAGES for the whole module when it is a test file.

    A raw checker runs after pylint reads the module's own pragmas and before
    the AST walk that emits the three messages. The checker marks the messages
    off on every line of the file. A module-scope disable on line 1 is not
    enough: when line 1 is an import, pylint limits that disable to the line.
    """

    name = 'muma-test-layout'
    # Pylint only runs a checker that has an enabled message. This one is
    # never emitted; it exists so the checker runs, and an info message does
    # not count in the score. ``--disable=all`` switches the plugin off too.
    msgs = {
        'I9901': (
            'Test-layout checks are disabled in this test file',
            'muma-test-layout',
            'Placeholder that keeps the muma-test-layout checker active.',
        ),
    }

    def process_module(self, node: nodes.Module) -> None:
        """Disable the layout messages for ``node`` if it is a test file."""
        if not is_test_file(node.file):
            return
        file_state = self.linter.file_state
        last_line = node.tolineno or 1
        for symbol in TEST_LAYOUT_MESSAGES:
            for definition in self.linter.msgs_store.get_message_definitions(symbol):
                for line in range(1, last_line + 1):
                    file_state.set_msg_status(definition, line, False, scope='line')


def register(linter: PyLinter) -> None:
    """Pylint entry point: add the checker to ``linter``."""
    linter.register_checker(TestLayoutChecker(linter))
