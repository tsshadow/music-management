"""Guard: nothing but services/common/import_queue.py knows where the import queue is.

The queue has always lived inside the label tree, at `<eps root>/__TODO`, so every walker of
`EPs/*` had to know to skip it -- and the tagger once did not, stamping `__TODO` into files as their
record label (bug reports 030 and 087). The walkers now ask `ImportQueue` instead of comparing
names, which is what lets the queue move out of the tree with a config change. This check keeps a
new walker from spelling the name out again: any string literal containing it, outside a docstring
and outside the module that owns it, fails here.
"""

import ast
from pathlib import Path

from tests.ci.conftest import REPO_ROOT

NEEDLE = '__todo'
OWNER = Path('services/common/import_queue.py')
SCANNED_TREES = ('services', 'tools', 'scripts')
SKIPPED_PARTS = {
    'node_modules',
    '.venv',
    'tests',
    'music-management-server',
    'muma-mobile',
    'frontend',
    # Deprecated and never run; see services/ml-analyzer/DEPRECATED.md.
    'ml-analyzer',
}
#: Files that may name the legacy location, and why.
ALLOWED = {
    # The one-shot migration that moves `EPs/__TODO` to `import`: the old location *is* its input.
    Path('scripts/restructure_music_folders.py'),
}
#: The walkers of the label tree that must ask ImportQueue (bug report 087).
WALKERS = (
    Path('services/tagger/tagger.py'),
    Path('services/common/channels.py'),
    Path('services/importer/label_resolver.py'),
    Path('tools/fix_nested_ep_dirs.py'),
    Path('scripts/backfill_label_from_path.py'),
)


def _is_test_file(path: Path) -> bool:
    return path.name.startswith('test_') or path.stem.endswith('Test') or path.name == 'conftest.py'


def _python_files():
    for tree in SCANNED_TREES:
        for path in sorted((REPO_ROOT / tree).rglob('*.py')):
            relative = path.relative_to(REPO_ROOT)
            if SKIPPED_PARTS & set(relative.parts) or _is_test_file(relative):
                continue
            yield relative


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def offending_literals(source: str) -> list[int]:
    """Line numbers of string literals (docstrings excluded) that spell the queue's name."""
    tree = ast.parse(source)
    docstrings = _docstring_ids(tree)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and NEEDLE in node.value.lower()
    ]


def test_the_checker_sees_a_literal_and_ignores_a_docstring():
    source = '"""Skips __TODO."""\nQUEUE = "/mnt/music/EPs/__TODO"\nx = f"{1}__todo"\n'
    assert offending_literals(source) == [2, 3]


def test_no_walker_hard_codes_the_import_queue():
    offenders = []
    for relative in _python_files():
        if relative == OWNER or relative in ALLOWED:
            continue
        for line in offending_literals((REPO_ROOT / relative).read_text(encoding='utf-8')):
            offenders.append(f'{relative}:{line}')
    assert not offenders, (
        'These spell out the import queue instead of asking services.common.import_queue.ImportQueue '
        '(bug report 087): ' + ', '.join(offenders)
    )


def test_every_known_walker_asks_the_shared_predicate():
    for relative in WALKERS:
        source = (REPO_ROOT / relative).read_text(encoding='utf-8')
        assert 'services.common.import_queue' in source, f'{relative} no longer uses ImportQueue'


def test_the_label_walk_no_longer_decides_by_a_leading_underscore_alone():
    """The underscore rule lives in ImportQueue.is_label_folder now, next to the queue check."""
    for relative in (Path('services/tagger/tagger.py'), Path('scripts/backfill_label_from_path.py')):
        source = (REPO_ROOT / relative).read_text(encoding='utf-8')
        assert ".startswith('_')" not in source, f'{relative} decides "is a label" on its own again'
