"""Where the import queue is, and the one test every walker of the label tree asks.

The import queue -- the folder the importer extracts releases into and the Mover empties into
`<eps root>/<label>/` -- has always lived *inside* the label tree, at `<eps root>/__TODO`. Every
component that walks `<eps root>/*` treating each folder as a record label therefore had to know
to skip it, and each one was a place to forget: the tagger forgot once, and wrote `__TODO` into
files as their record label (bug report 030). The scanner, the backfills and the resolver each grew
their own copy of the rule, some keyed on the literal name, some on a leading underscore.

This module is the only place that knows where the queue is. It reads `import_folder_path`, and
when that is unset falls back to `<eps_folder_path>/__TODO`, which is where it has always been. A
walker asks `ImportQueue.contains(path)` or `ImportQueue.is_label_folder(path)` instead of
comparing names, so moving the queue out of the label tree is a config change plus a file move,
not a code change (bug report 087, `docs/designs/todo-label-backlog/`).

`LEGACY_QUEUE_NAME` stays meaningful after such a move: files tagged before 2026-07-28 carry it as
their publisher whatever the queue is called today, so it is a placeholder value forever.
`tests/ci/test_import_queue_predicate.py` fails when any other module spells it out.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from services.common.label_names import looks_like_release_folder

#: The queue's historical folder name, and the value the tagger stamped into files as their
#: publisher while they waited in it. The only place in the code base allowed to spell it.
LEGACY_QUEUE_NAME = '__TODO'

#: A label folder whose name starts with this is not a label: `__Free&None` holds releases that
#: have none, and the queue itself started with it. Such folders are tagged as generic songs.
NON_LABEL_FOLDER_PREFIX = '_'

# `LabelSong.calculate_copyright` wrote "<publisher> (<year>)", so a poisoned publisher left a
# poisoned copyright behind it -- and the copyright is only computed when absent, so fixing the
# publisher never fixed it.
_COPYRIGHT_YEAR = re.compile(r'^(?P<holder>.*?)\s*\(\d{4}\)$')


def _text(value: Any) -> str:
    """`value` when it is a non-blank string, else ''.

    Settings are MagicMocks in half the test suite and a mock attribute is not a path; treating
    anything that is not a string as unset keeps the fallback working there too.
    """
    return value.strip() if isinstance(value, str) else ''


def _norm(path: str) -> str:
    return os.path.normpath(path) if path else ''


@dataclass(frozen=True)
class ImportQueue:
    """The import queue's location, and the questions walkers ask about it.

    `path` is normalised but not resolved: resolving goes to the filesystem, which on the CIFS
    share is a round trip per call. A caller comparing against resolved paths resolves this path
    once itself (see `resolved`).
    """

    path: str

    @classmethod
    def from_settings(cls, settings: Any = None) -> ImportQueue:
        """The queue as configured: `import_folder_path`, else `<eps_folder_path>/__TODO`."""
        if settings is None:
            from services.common.config_store import ConfigStore

            settings = ConfigStore()
        configured = _text(getattr(settings, 'import_folder_path', ''))
        if configured:
            return cls(_norm(configured))
        eps_root = _text(getattr(settings, 'eps_folder_path', ''))
        if eps_root:
            return cls(_norm(os.path.join(eps_root, LEGACY_QUEUE_NAME)))
        return cls('')

    def resolved(self) -> ImportQueue:
        """The same queue with its path resolved, for comparing against resolved paths."""
        if not self.path:
            return self
        try:
            return ImportQueue(str(os.path.realpath(self.path)))
        except (OSError, RuntimeError):
            return self

    @property
    def name(self) -> str:
        """The queue folder's own name: what a release still waiting in it was stamped with."""
        return os.path.basename(self.path) if self.path else ''

    def contains(self, path: str | os.PathLike[str] | None) -> bool:
        """Whether `path` is the queue itself or anything below it."""
        if not self.path or not path:
            return False
        candidate = _norm(os.fspath(path))
        return candidate == self.path or candidate.startswith(self.path.rstrip(os.sep) + os.sep)

    def lies_within(self, root: str | os.PathLike[str] | None) -> bool:
        """Whether the queue sits inside `root` -- true today for the EPs root, false after the move."""
        if not self.path or not root:
            return False
        base = _norm(os.fspath(root)).rstrip(os.sep)
        return self.path.startswith(base + os.sep)

    def is_label_folder(self, folder: str | os.PathLike[str]) -> bool:
        """Whether a folder directly under the label tree names a record label.

        Neither the queue nor an underscore folder does. The underscore rule stays because
        `__Free&None` needs it; the queue is refused by location, so it keeps being refused
        whatever it is renamed to.
        """
        if self.contains(folder):
            return False
        return not os.path.basename(_norm(os.fspath(folder))).startswith(NON_LABEL_FOLDER_PREFIX)

    def placeholder_values(self) -> set[str]:
        """Lowercased publisher values that mean "was in the queue", never "is on this label"."""
        values = {LEGACY_QUEUE_NAME.lower()}
        if self.name:
            values.add(self.name.lower())
        return values

    def is_placeholder_publisher(self, value: str | None) -> bool:
        """Whether a publisher tag holds a folder's name instead of a label.

        Three kinds, all left by deriving the label from the path (bug reports 030 and 146): the
        queue's name; the name of a folder that is no label, which starts with `_` exactly as
        `is_label_folder` refuses it (`__Free&None`, and `___Free&None` from before it was
        renamed); and a release folder's name, taken when the depth was off by one
        (`label_names.looks_like_release_folder`).
        """
        text = _text(value)
        if not text:
            return False
        return (
            text.lower() in self.placeholder_values()
            or text.startswith(NON_LABEL_FOLDER_PREFIX)
            or looks_like_release_folder(text)
        )

    def is_placeholder_copyright(self, value: str | None) -> bool:
        """Whether a copyright tag was computed from a placeholder publisher ("__TODO (2021)")."""
        text = _text(value)
        if not text:
            return False
        match = _COPYRIGHT_YEAR.match(text)
        holder = match.group('holder') if match else text
        return self.is_placeholder_publisher(holder)
