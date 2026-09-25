"""Finds the files still stamped `__TODO` as their record label, and queues them for a retag.

Before 2026-07-28 the tagger ran LabelSong over releases waiting in the import queue and wrote the
queue's own folder name in as their publisher, and "__TODO (<year>)" as their copyright (bug report
030). The cause is fixed; the files are not. Some still wait in the queue, where GenericSong never
touched the publisher; some have since been moved into a label folder, where LabelSong rewrote the
publisher but kept the copyright, because it only computes one when there is none.

This module does not write a tag. It walks the files the tagger knows below the label tree (and
below the import queue, if that has moved out of it) one page at a time, reads each file's publisher
and copyright, and for every poisoned file works out what its label *should* be from the folder it
lives in now:

  * in a label folder (`<eps root>/<label>/...`): that label -- exactly what LabelSong writes;
  * still in the import queue: what the importer's own resolver proposes for its release folder
    (`services.importer.label_resolver.resolve`, from the release's tags and .nfo, with the same
    blacklist), or undecidable when it proposes nothing;
  * in an underscore folder such as `__Free&None`: no label at all.

Apply mode hands the poisoned files to the tagger queue with reason `todo_label_repair`
(`ProcessedFilesHelper.mark_paths_for_rescan`), never retagging inline: the five-minute tagger round
does the writing, and `DropQueuePlaceholderRule` plus LabelSong are what it writes. A retag never
writes the resolver's proposal into a file -- a release in the queue gets that label only once a
person confirms the proposal and it is moved. So an undecidable file is still queued: the retag only
empties the placeholder, which is right whatever the label turns out to be.

Re-runnable: a repaired file no longer carries the placeholder, so a second pass finds only what the
first one missed. See docs/designs/todo-label-backlog/ and bug report 087.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.common.import_queue import ImportQueue
from services.importer import label_resolver

#: The rescan reason the repair queues under. Not a bulk reason, so it is served before
#: `rescan_all`/`deep_run` but after nothing a person decided -- see pending_reasons.
REASON = 'todo_label_repair'

DEFAULT_PAGE = 300
MAX_PAGE = 2000
#: How many undecidable paths one page reports; the counts are always complete.
UNDECIDABLE_SAMPLE = 200

AREA_LABEL = 'label'
AREA_QUEUE = 'queue'
AREA_NO_LABEL = 'no_label'
AREA_OUTSIDE = 'outside'


@dataclass(frozen=True)
class Finding:
    """One poisoned file: which tags carry the placeholder and what the label should be."""

    path: str
    fields: tuple[str, ...]
    area: str
    label: str | None
    source: str

    @property
    def decidable(self) -> bool:
        """Whether the folder (or the resolver) names the label, or says there is none."""
        return self.label is not None or self.area == AREA_NO_LABEL


def read_label_tags(path: str) -> tuple[str, str]:
    """`(publisher, copyright)` as the tagger itself reads them, or two empty strings.

    ReadonlySong rather than label_resolver.read_tags: the question is "what will the tagger
    see", and ReadonlySong maps each container's key for PUBLISHER/COPYRIGHT the way the tagger
    does. Imported here because loading it pulls in the tagger's rule machinery.
    """
    from services.scanner.Song.ReadonlySong import ReadonlySong

    try:
        song = ReadonlySong(path)
        if not hasattr(song, 'tag_collection'):
            return ('', '')
        return (song.publisher() or '', song.copyright() or '')
    except Exception:  # noqa: BLE001 - an unreadable file is not poisoned as far as we can tell
        return ('', '')


def _first_component(path: str, root: str) -> str | None:
    root = os.path.normpath(root)
    path = os.path.normpath(path)
    if not path.startswith(root.rstrip(os.sep) + os.sep):
        return None
    parts = [part for part in path[len(root) :].split(os.sep) if part]
    return parts[0] if len(parts) > 1 else None


class TodoLabelRepair:
    """Pages through the label tree, classifying poisoned files and optionally queueing them."""

    def __init__(
        self,
        settings: Any = None,
        processed_files: Any = None,
        reader: Callable[[str], tuple[str, str]] = read_label_tags,
        resolver: Callable[..., label_resolver.LabelProposal] = label_resolver.resolve,
    ):
        if settings is None:
            from services.common.config_store import ConfigStore

            settings = ConfigStore()
        if processed_files is None:
            from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper

            processed_files = ProcessedFilesHelper()
        self.eps_root = os.path.normpath(str(settings.eps_folder_path or '')) if settings.eps_folder_path else ''
        self.queue = ImportQueue.from_settings(settings)
        self.processed_files = processed_files
        self.reader = reader
        self.resolver = resolver
        self._proposals: dict[str, label_resolver.LabelProposal] = {}

    def roots(self) -> list[str]:
        """The subtrees to walk: the label tree, and the queue if it no longer lies inside it."""
        roots = [self.eps_root] if self.eps_root else []
        if self.queue.path and not self.queue.lies_within(self.eps_root):
            roots.append(self.queue.path)
        return roots

    def derive(self, path: str) -> tuple[str, str | None, str]:
        """`(area, label, source)` for a file, from the folder it lives in now."""
        if self.queue.contains(path):
            release = _first_component(path, self.queue.path)
            if release is None:
                return (AREA_QUEUE, None, 'none')
            proposal = self._proposal(os.path.join(self.queue.path, release))
            return (AREA_QUEUE, proposal.label, proposal.source)
        folder = _first_component(path, self.eps_root) if self.eps_root else None
        if folder is None:
            return (AREA_OUTSIDE, None, 'none')
        if self.queue.is_label_folder(os.path.join(self.eps_root, folder)):
            return (AREA_LABEL, folder, 'folder')
        return (AREA_NO_LABEL, None, 'folder')

    def _proposal(self, release_path: str) -> label_resolver.LabelProposal:
        """The importer's proposal for one release folder, read once per release per repair."""
        if release_path not in self._proposals:
            self._proposals[release_path] = self.resolver(release_path, import_folder_name=self.queue.name)
        return self._proposals[release_path]

    def classify(self, path: str) -> Finding | None:
        """A Finding when the file carries the placeholder, else None."""
        publisher, copyright_ = self.reader(path)
        fields = []
        if self.queue.is_placeholder_publisher(publisher):
            fields.append('publisher')
        if self.queue.is_placeholder_copyright(copyright_):
            fields.append('copyright')
        if not fields:
            return None
        area, label, source = self.derive(path)
        return Finding(path, tuple(fields), area, label, source)

    def run_page(self, after: str = '', limit: int = DEFAULT_PAGE, apply: bool = False) -> dict[str, Any]:
        """Classify one page of known files; in apply mode, queue the poisoned ones.

        Returns the page's counts and `next_after`, the cursor for the next call, and `done`
        once a page came back short. Counts are per page; the caller adds them up.
        """
        limit = max(1, min(int(limit), MAX_PAGE))
        paths = self.processed_files.paths_under(self.roots(), after, limit)
        findings = [finding for finding in (self.classify(path) for path in paths) if finding]
        by_label: Counter[str] = Counter()
        by_area: Counter[str] = Counter()
        by_field: Counter[str] = Counter()
        undecidable: list[str] = []
        for finding in findings:
            by_area[finding.area] += 1
            by_field.update(finding.fields)
            if finding.label is not None:
                by_label[finding.label] += 1
            elif not finding.decidable:
                undecidable.append(finding.path)
        queued = 0
        if apply and findings:
            queued = self.processed_files.mark_paths_for_rescan([finding.path for finding in findings], REASON)
        return {
            'mode': 'apply' if apply else 'dry-run',
            'reason': REASON,
            'roots': self.roots(),
            'scanned': len(paths),
            'poisoned': len(findings),
            'by_area': dict(by_area),
            'by_field': dict(by_field),
            'by_label': dict(by_label.most_common()),
            # Every poisoned path of the page, so a guided run can back up exactly the rows it
            # is about to queue. Bounded by `limit`.
            'poisoned_paths': [finding.path for finding in findings],
            'undecidable_count': len(undecidable),
            'undecidable': undecidable[:UNDECIDABLE_SAMPLE],
            'queued': queued,
            'next_after': paths[-1] if paths else after,
            'done': len(paths) < limit,
        }
