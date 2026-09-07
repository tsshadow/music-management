"""Where the pipeline parks what it would otherwise delete.

Four places in the import and tagging path remove data outright, and each is a judgement
call that can be wrong:

- `Extractor.run` removes the source archive the moment extraction succeeds -- before the
  release has been tagged, moved or scanned. For a label rip that archive is the only
  pristine copy of the release there will ever be.
- `Mover` removes a source folder it judges to be a duplicate. `is_same_release` compares
  relative names and sizes, not contents, so two different releases that happen to agree
  on both are indistinguishable to it.
- `Renamer` does the same when a rename collides.
- `BaseSong.__init__` deletes an `.m4a` mutagen cannot parse.

None of those decisions is worth an irreversible delete. Moving the file instead costs a
rename on the same filesystem and buys the retention window back.

Deliberately not a backup, and not a substitute for one. It holds what the pipeline chose
to discard, for as long as `quarantine_retention_days`, and `sweep()` then removes it --
otherwise this quietly becomes the thing that fills the disk, which is the failure it is
supposed to prevent.

Every function here is best effort. A quarantine that raises would turn a recoverable
"could not park this" into a failed import, which is a worse outcome than the delete it
replaced.
"""

import logging
import os
import shutil
from datetime import date, datetime, timedelta

from services.common.config_store import ConfigStore as Settings

#: Sub-folder of the quarantine root, so what parked something is visible without a log.
EXTRACTED_ARCHIVE = 'extracted-archive'
DUPLICATE_RELEASE = 'duplicate-release'
UNREADABLE_FILE = 'unreadable-file'

_DAY_FORMAT = '%Y-%m-%d'


def _absolute_path(value) -> str | None:
    """A configured path, or None when it is not one.

    Two things are refused rather than used. A value that is not a string at all -- a
    stubbed setting hands back an object whose `str()` is `<MagicMock ...>`, and
    `os.makedirs` will happily create a directory by that name. And a relative path,
    which would put the quarantine wherever the process happens to be running: for the
    importer that is the repository root, and it created four such directories there
    before this guard existed.
    """
    if not isinstance(value, str):
        return None
    path = value.strip()
    if not path or not os.path.isabs(path):
        return None
    return path


def root() -> str | None:
    """The quarantine root, or None when there is nowhere sensible to put one.

    Falls back to `.quarantine` beside the music root rather than requiring the setting:
    the callers are delete paths, and one unset value must not turn them back into
    deletes.
    """
    settings = Settings()
    configured = _absolute_path(getattr(settings, 'quarantine_folder_path', None))
    if configured:
        return configured
    music = _absolute_path(getattr(settings, 'music_folder_path', None))
    if not music:
        return None
    return os.path.join(music.rstrip(os.sep), '.quarantine')


def retention_days() -> int:
    try:
        days = int(getattr(Settings(), 'quarantine_retention_days', 30))
    except (TypeError, ValueError):
        return 30
    # Zero or negative would sweep what was parked seconds ago, which is the delete this
    # module exists to replace.
    return days if days > 0 else 30


def _destination(category: str, name: str) -> str | None:
    base = root()
    if not base:
        logging.warning('No quarantine folder configured and no music root to derive one from')
        return None
    folder = os.path.join(base, date.today().strftime(_DAY_FORMAT), category)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, name)
    if not os.path.exists(target):
        return target
    # Two releases with the same folder name park on the same day more often than it
    # sounds -- that is exactly the case the mover calls a duplicate.
    stamp = datetime.now().strftime('%H%M%S')
    return os.path.join(folder, f'{name}.{stamp}')


def put(path: str, category: str) -> str | None:
    """Move a file or folder into quarantine. Returns where it went, or None.

    None means the caller's data is still at `path`: leaving it there is the safe failure,
    and every caller treats it that way rather than falling back to a delete.
    """
    if not path or not os.path.exists(path):
        return None
    target = _destination(category, os.path.basename(path.rstrip(os.sep)))
    if not target:
        return None
    try:
        shutil.move(path, target)
    except Exception as e:
        logging.error('Could not quarantine %s: %s', path, e)
        return None
    logging.info('Quarantined %s -> %s', path, target)
    return target


def sweep(retention: int | None = None) -> int:
    """Remove day folders past the retention window. Returns how many were removed.

    Called from the importer's own cycle rather than from a timer, so the sweep runs on
    the same schedule as the thing that fills it.
    """
    base = root()
    if not base or not os.path.isdir(base):
        return 0
    cutoff = date.today() - timedelta(days=retention if retention is not None else retention_days())
    removed = 0
    for name in sorted(os.listdir(base)):
        try:
            day = datetime.strptime(name, _DAY_FORMAT).date()
        except ValueError:
            # Not a day folder. Somebody put something here by hand; leave it alone.
            continue
        if day > cutoff:
            continue
        try:
            shutil.rmtree(os.path.join(base, name))
            removed += 1
            logging.info('Swept quarantine folder %s (older than %s)', name, cutoff.isoformat())
        except OSError as e:
            logging.warning('Could not sweep quarantine folder %s: %s', name, e)
    return removed
