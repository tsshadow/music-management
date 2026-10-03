"""Whether a release folder still holds music, or only the scene files that came with it.

A scene release is its audio plus a handful of companions: `00-<release>.m3u`, `.nfo`, `.sfv`,
a cover `.jpg`. When the audio is gone, the companions stay behind as a folder that is no use to
anyone, and LMS reports its playlist as `playlist-all-entries-missing` after every library scan
(GitLab issue #167, bug report 121). The importer's mover deletes such a folder from the import
queue instead of placing it in the library; `scripts/prod/person/delete-audio-less-release-folders.sh`
clears the ones that are already there.

The rule leans towards keeping. A folder is audio-less only when every file anywhere below it is a
known companion kind (an image or a document, see the extension lists below) or housekeeping the
OS or the NAS drops everywhere, and at least one such file exists. Any of these keeps the folder:

* an audio file at any depth, so a release whose tracks sit in `CD1/` and `CD2/` stays;
* an archive (`.zip`, `.rar`, a `.r00` volume, ...): it has not been extracted yet, and it may
  well hold the audio;
* any other file, such as a video or an extension nobody listed: a person should look at it;
* a symbolic link, file or directory: the walk does not follow it, so it cannot see what is
  behind it;
* a folder that cannot be read completely, or that holds no file at all.

Lives in `services/common` because the music-manager image, where the person script runs, does
not have `services.importer`.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Final

from services.common.Helpers.ReleaseFolder import AUDIO_EXTENSIONS
from services.common.import_queue import ImportQueue

#: Images a release or a download brings along: covers, scans, artwork.
IMAGE_EXTENSIONS: Final = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.heic')

#: Text that describes a release rather than being it: the scene `.nfo`, `.sfv` and `.m3u`, a
#: cue sheet, a rip log, a booklet.
DOCUMENT_EXTENSIONS: Final = (
    '.pdf', '.txt', '.nfo', '.doc', '.docx', '.rtf', '.md', '.html', '.htm', '.csv', '.xls', '.xlsx',
    '.cue', '.m3u', '.m3u8', '.log', '.sfv', '.json', '.xml',
)  # fmt: skip

#: Housekeeping files an OS or the NAS drops into any folder.
IGNORED_NAMES: Final = frozenset({'thumbs.db', 'desktop.ini'})

#: Synology's thumbnail folder: the NAS writes it on its own, and it says nothing about the release.
SYNOLOGY_FOLDER: Final = '@eaDir'

#: Archive suffixes the extractor knows, and the volumes of a split RAR set.
ARCHIVE_EXTENSIONS: Final = ('.zip', '.rar', '.7z', '.tar', '.tgz', '.tbz', '.tbz2', '.txz', '.gz', '.bz2', '.xz')
_RAR_VOLUME = re.compile(r'\.[rs]\d{2}$', re.IGNORECASE)

#: Verdicts of `inspect`. Only AUDIO_LESS may be deleted.
AUDIO_LESS: Final = 'audio-less'
HOLDS_AUDIO: Final = 'audio'
HOLDS_ARCHIVE: Final = 'archive'
HOLDS_OTHER: Final = 'other'
HOLDS_LINK: Final = 'link'
EMPTY: Final = 'empty'
UNREADABLE: Final = 'unreadable'


@dataclass(frozen=True)
class FolderVerdict:
    """What `inspect` found in one folder.

    `files` lists the companion files (relative paths) for AUDIO_LESS. For the other kinds
    `detail` names the first file that decided it, or the error.
    """

    kind: str
    files: tuple[str, ...] = field(default_factory=tuple)
    detail: str = ''

    @property
    def audio_less(self) -> bool:
        """Whether the folder holds only companion files, so deleting it loses no music."""
        return self.kind == AUDIO_LESS


def _kind_of(name: str) -> str | None:
    """HOLDS_AUDIO, HOLDS_ARCHIVE or HOLDS_OTHER for a file that decides the folder; None for a companion."""
    lower = name.lower()
    if lower.endswith(AUDIO_EXTENSIONS):
        return HOLDS_AUDIO
    if lower.endswith(ARCHIVE_EXTENSIONS) or _RAR_VOLUME.search(lower):
        return HOLDS_ARCHIVE
    if lower.startswith('.') or lower in IGNORED_NAMES or lower.endswith(IMAGE_EXTENSIONS + DOCUMENT_EXTENSIONS):
        return None
    return HOLDS_OTHER


def _raise(error: OSError) -> None:
    raise error


def inspect(path: str) -> FolderVerdict:
    """Walks `path` completely and says whether it is audio-less; see the module docstring.

    Audio decides first: a folder with a track and a video is HOLDS_AUDIO, the kind that matters
    most when someone reads why a folder was kept.
    """
    if os.path.islink(path):
        return FolderVerdict(HOLDS_LINK, detail=os.path.basename(path))
    companions: list[str] = []
    first_keep: tuple[str, str] | None = None
    try:
        for root, dirs, files in os.walk(path, onerror=_raise):
            for directory in dirs:
                if os.path.islink(os.path.join(root, directory)):
                    return FolderVerdict(HOLDS_LINK, detail=os.path.relpath(os.path.join(root, directory), path))
            in_thumbnails = SYNOLOGY_FOLDER in os.path.relpath(root, path).split(os.sep)
            for name in files:
                full = os.path.join(root, name)
                relative = os.path.relpath(full, path)
                if os.path.islink(full):
                    return FolderVerdict(HOLDS_LINK, detail=relative)
                kind = _kind_of(name)
                if kind == HOLDS_AUDIO:
                    return FolderVerdict(HOLDS_AUDIO, detail=relative)
                if in_thumbnails:
                    continue
                if kind is None:
                    companions.append(relative)
                elif first_keep is None:
                    first_keep = (kind, relative)
    except OSError as e:
        return FolderVerdict(UNREADABLE, detail=str(e))
    if first_keep is not None:
        return FolderVerdict(first_keep[0], detail=first_keep[1])
    if not companions:
        return FolderVerdict(EMPTY)
    return FolderVerdict(AUDIO_LESS, files=tuple(sorted(companions)))


def is_queue_release(queue: ImportQueue, path: str) -> bool:
    """Whether `path` is a folder directly inside the import queue, and not a link.

    Compared on resolved paths, so neither a symbolic link nor a `..` can lead a delete out of
    the queue. The queue itself is not a release in it, and neither is anything outside it.
    """
    if not queue.path or os.path.islink(path):
        return False
    real = os.path.realpath(path)
    return os.path.dirname(real) == os.path.realpath(queue.path) and real != os.path.realpath(queue.path)


def delete_from_queue(queue: ImportQueue, path: str) -> FolderVerdict | None:
    """Deletes `path` when it is an audio-less release folder in the import queue.

    Checks both again right before it deletes, whatever the caller found earlier. Returns the
    verdict the folder was deleted on, or None when it was kept; an `OSError` from the delete
    itself is the caller's to report.
    """
    if not is_queue_release(queue, path):
        return None
    verdict = inspect(path)
    if not verdict.audio_less:
        return None
    shutil.rmtree(path)
    return verdict
