"""Resolves the label and catalog number a label release carries in its path.

The library layout is `<eps root>/<label>/<cat id - release>/<file>`, so the two folders above
a track name it. Scene releases regularly ship a second copy of the release folder inside itself,
which puts the audio one level deeper; counting parents up from the file then lands on the release
folder and stores that as the label. Anchoring on the EPs root keeps the label at the first
component no matter how deep the file sits below it.

Not every folder in that position names a label, though. The import queue and the folders starting
with `_` (`__Free&None`) hold releases that have none, and a release folder that sits directly in
the root -- or, outside the root, one level too deep -- is a release, not its label. Each of those
was once written into files as their publisher (bug reports 030 and 146); `split` answers no label
for them instead.
"""

from __future__ import annotations

import os

from services.common.catalogue_number import is_catalogue_number
from services.common.import_queue import ImportQueue
from services.common.label_names import looks_like_release_folder


def _names_a_label(folder_path: str, name: str, queue: ImportQueue) -> bool:
    """Whether the folder `name` at `folder_path` may be written into a file as its label."""
    return bool(name) and queue.is_label_folder(folder_path) and not queue.is_placeholder_publisher(name)


def split(path: str, eps_root: str | None, delimiter: str, queue: ImportQueue | None = None) -> tuple[str, str]:
    """Returns `(label, release folder)` for a label path; the label is '' when the path names none.

    Paths outside the EPs root - the importer works on its own folder - fall back to the two
    folders directly above the file, which is what the tagger did before the root was consulted.
    `queue` is the configured import queue; without one only the folder names are judged, which
    still refuses every underscore folder and every release-shaped name.
    """
    queue = queue or ImportQueue('')
    root = str(eps_root or '').rstrip(delimiter)
    if root and path.startswith(root + delimiter):
        parts = [part for part in path[len(root) + 1 :].split(delimiter) if part]
        if len(parts) < 2:
            return ('', '')
        top = parts[0]
        if looks_like_release_folder(top):
            # A release sitting directly in the root: its folder is the release, not a label.
            return ('', top)
        if not _names_a_label(os.path.join(root, top), top, queue):
            return ('', '')
        return (top, parts[1] if len(parts) >= 3 else '')
    parents = path.rsplit(delimiter, 2)
    if len(parents) < 3:
        return ('', '')
    label = parents[0].split(delimiter)[-1]
    if not _names_a_label(parents[0], label, queue):
        return ('', '')
    return (label, parents[1])


def catalog_number(release_folder: str) -> str:
    """The catalog number is the first space separated part of the release folder.

    A folder name without a space is a catalogue number only when it is nothing else
    (`FUSION001`). The importer prefixes `<cat id> - ` only when the release has one, and
    since bug report 145 it leaves every other name alone -- a whole scene name like
    `Guizcore_-_Coffee_Time-WEB-FLAC-2026` is not a catalogue number.
    """
    if ' ' not in release_folder:
        return release_folder if is_catalogue_number(release_folder) else ''
    return release_folder.split(' ')[0]
