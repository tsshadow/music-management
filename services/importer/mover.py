import logging
import os
import re
import shutil
from datetime import date, datetime
from os import listdir
from os.path import isfile, join

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers import Quarantine
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.common.Helpers.NotificationService import notification_service
from services.common.import_queue import ImportQueue
from services.common.store_lookup import Budget
from services.importer.conflict_store import MOVER, ConflictTracker
from services.importer.label_match import LabelIndex
from services.importer.label_proposal_store import NEW_ROW, LabelProposalStore, ProposalSnapshot, fingerprint
from services.importer.label_resolver import resolve
from services.importer.release_compare import is_same_release
from services.importer.release_info import Placement, ReleaseInfo
from services.importer.settle import folder_signature, is_settled, is_staging
from services.tagger.announce import announce
from services.tagger.Song.LabelSong import LabelSong


def get_cat_id(folder: str):
    """
    Extracts the catalog ID (CAT ID) from a folder name.
    - Takes the first space-separated part.
    - Keeps letters/numbers up to but not including at least 3 consecutive numbers.
    """
    if ' ' in folder:
        first_part = folder.split(' ')[0]
        if '247HC' in first_part:
            return '247HC'
        if 'R909' in first_part:
            return 'R909'
        if 'UNFD' in first_part:
            return 'UNFD'
        first_part = first_part.replace('_', '').replace('-', '')
        match = re.match('^([A-Za-z]*\\d*[A-Za-z]*)(?=\\d{3,})', first_part)
        if match:
            return match.group(1)
        return first_part
    return None


#: What the rest of the library carries. Everything that was in place on 2026-09-05 sits
#: at 0777/0666 after the ACL repair of that day, and every writer since -- the tagger, the
#: backfills, LMS -- assumes it can open a file for writing.
DIR_MODE = 0o777
FILE_MODE = 0o666


def make_library_writable(folder_path) -> int:
    """Give a freshly imported release the permissions the rest of the library has.

    The importer runs as root with the default umask, so what it unpacks and moves lands
    as root:root 0755/0644. Root itself never notices -- it may write anything -- so the
    import, the tagging pass and the scan all succeed, and the release looks perfectly
    healthy. Everyone else is locked out: over SMB the share's user gets `other::r--` and
    every later write fails with [Errno 13].

    Measured 2026-09-08: of the EPs directories touched since 2026-09-01, 631 were 0777
    and 19 were 0755 -- exactly the ones created after the last manual repair swept the
    tree. The release-date backfill hit 9 of their files and skipped them. A sweep fixes
    what exists at that moment and says nothing about tomorrow's import, which is why this
    belongs here rather than in a script.

    Best effort, and it says so when it fails: a mode that will not stick is worth a log
    line, not a failed import. The release is already in place by the time this runs, and
    refusing it afterwards would leave the library in a worse state than a readable file.

    Returns the number of paths it could not change.
    """
    failures = 0
    for root, dirs, files in os.walk(folder_path):
        for name, mode in [(directory, DIR_MODE) for directory in dirs] + [(file, FILE_MODE) for file in files]:
            path = os.path.join(root, name)
            try:
                os.chmod(path, mode)
            except OSError as e:
                failures += 1
                logging.warning(f'Could not set permissions on {path}: {e}')
    try:
        os.chmod(folder_path, DIR_MODE)
    except OSError as e:
        failures += 1
        logging.warning(f'Could not set permissions on {folder_path}: {e}')
    return failures


def post_processing_songs(folder_path, arrival_date: date | None = None) -> int:
    """
    Call LabelSong(path) for every supported audio file in the folder,
    excluding Synology's @eaDir directories and non-files.

    Every tagged file is recorded in the event log, without a push: one per file was
    100+ phone notifications for a single weekly pack. The mover sends one push per
    release instead, which is why this returns how many files were tagged.

    `arrival_date` is the day the release first arrived in the import queue; the date
    ladder may use it for a new release that carries nothing better than its year
    (docs/designs/release-info-enrichment/).
    """
    supported_exts = ('.mp3', '.flac', '.m4a', '.aac', '.wav')
    tagged = 0
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d != '@eaDir']
        for file in files:
            if file.lower().endswith(supported_exts):
                full_path = os.path.join(root, file)
                if not os.path.isfile(full_path):
                    logging.warning(f'Skipping non-file: {full_path}')
                    continue
                try:
                    logging.info(f'Processing file with LabelSong: {full_path}')
                    s = LabelSong(str(full_path))
                    s.arrival_date = arrival_date
                    s.parse()
                    # The walk would otherwise tag the release a second time on its next
                    # pass; and the scanner learns of it now rather than on the hour.
                    announce(full_path)
                    notification_service.notify(str(s), title='Track Imported', push=False)
                    tagged += 1
                except Exception as e:
                    logging.error(f'Failed to process {full_path} with LabelSong: {e}')
    return tagged


def release_summary(folder: str, label: str, tracks: int, placement: Placement | None = None) -> str:
    """The one push a release gets: label, catalogue number and how many tracks were imported.

    The catalogue number is the part of the folder name before the renamer's ` - `, which
    is the full number (`SCAN123`) rather than the prefix the label was looked up by. A
    release placed by the label its .nfo or store names says so, and what it said.
    """
    catalog = folder.split(' - ', 1)[0].strip() if ' - ' in folder else ''
    lines = [folder, f'Label: {label}']
    if placement is not None:
        lines.append(f'Label from: {placement.source} ({placement.stated})')
    if catalog:
        lines.append(f'Catalog: {catalog}')
    lines.append(f'Tracks: {tracks}')
    return '\n'.join(lines)


#: Defaults of the release-info settings (ConfigStore group "Importer").
PLACE_BY_LABEL_NAME_DEFAULT = True
STORE_LOOKUPS_DEFAULT = True
STORE_LOOKUPS_PER_CYCLE_DEFAULT = 60
LABEL_NAME_MOVES_PER_CYCLE_DEFAULT = 50


def _setting_bool(settings, key: str, default: bool) -> bool:
    """A boolean setting; anything that is not clearly a boolean is the default."""
    value = getattr(settings, key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ('1', 'true', 'yes', 'on', '0', 'false', 'no', 'off'):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return default


def _setting_int(settings, key: str, default: int) -> int:
    """A non-negative whole-number setting; anything else is the default."""
    value = getattr(settings, key, default)
    if isinstance(value, bool) or not isinstance(value, int | str):
        return default
    try:
        number = int(value)
    except ValueError:
        return default
    return number if number >= 0 else default


class Mover:
    """Moves every settled release folder in the import folder to its label, and tags it there.

    A release no catalogue rule routes goes to the existing label folder its .nfo (or the
    Deezer album the .nfo links) names, when exactly one folder matches and
    `import_place_by_label_name` is on (docs/designs/release-info-enrichment/).
    """

    def __init__(self):
        self.settings = Settings()
        self.db_connector = DatabaseConnector()
        self.proposals = LabelProposalStore()
        #: folder -> signature when its label was last resolved by this process. Only
        #: consulted when the proposal table cannot be read; see `_propose`.
        self._resolved: dict[str, str] = {}
        #: The proposal rows and rules version this cycle compares against.
        self._snapshot: ProposalSnapshot | None = None
        #: Unplaceable folders this cycle: seen, skipped as unchanged, and read again.
        self._counts = {'checked': 0, 'skipped': 0, 'reread': 0}
        #: Standing conflicts, so each one is warned about once rather than every cycle.
        self.conflicts = ConflictTracker(MOVER)
        #: The .nfo facts per folder, shared with the Renamer when the service passes it in.
        self.release_info = ReleaseInfo()
        #: This cycle's label folders, store-lookup budget and label-name moves left.
        self._index: LabelIndex | None = None
        self._budget: Budget | None = None
        self._name_moves_left = 0

    def _begin_release_info_cycle(self):
        """Fresh label index and budgets for one cycle."""
        self._index = None
        lookups = _setting_bool(self.settings, 'import_store_lookups', STORE_LOOKUPS_DEFAULT)
        per_cycle = _setting_int(self.settings, 'import_store_lookups_per_cycle', STORE_LOOKUPS_PER_CYCLE_DEFAULT)
        self._budget = Budget(per_cycle) if lookups else None
        self._name_moves_left = _setting_int(
            self.settings, 'import_label_name_moves_per_cycle', LABEL_NAME_MOVES_PER_CYCLE_DEFAULT
        )

    def _label_index(self) -> LabelIndex:
        """The label folders of this cycle, listed once."""
        if self._index is None:
            self._index = LabelIndex.from_library(
                self.settings.eps_folder_path, ImportQueue.from_settings(self.settings), self.db_connector.connection
            )
        return self._index

    def _place(self, folder, dry_run) -> bool:
        """Move a release no rule routes to the label folder its .nfo or store names. True when moved."""
        if not _setting_bool(self.settings, 'import_place_by_label_name', PLACE_BY_LABEL_NAME_DEFAULT):
            return False
        if self._name_moves_left <= 0:
            return False
        src = join(self.settings.import_folder_path, folder)
        try:
            placement = self.release_info.placement(src, self._label_index(), self._budget)
        except Exception as e:  # noqa: BLE001 - enrichment is optional, the proposal path still works
            logging.warning(f'Could not read the release info of {folder}: {e}')
            return False
        if placement is None:
            return False
        logging.info(f'Placing {folder} under {placement.label}: {placement.source} says {placement.stated!r}')
        self._name_moves_left -= 1
        self._move_to_label(folder, placement.label, dry_run, placement)
        return True

    def _arrival(self, folder) -> date:
        """The day the release first arrived: its proposal row's creation, else today."""
        row = self._snapshot.rows.get(folder) if self._snapshot is not None else None
        created = getattr(row, 'created_at', None)
        if isinstance(created, datetime):
            return created.date()
        if isinstance(created, date):
            return created
        return date.today()

    def _is_backlog(self, folder) -> bool:
        """Whether the folder already waited a cycle as unplaceable: it has a proposal row."""
        return self._snapshot is not None and folder in self._snapshot.rows

    def _propose(self, folder, cat_id, warning):
        """
        Record a release this step could not place, so it can be reviewed once instead
        of re-warned on every cycle for as long as it sits in the import folder.

        Resolving reads the tags of every track, over CIFS, and ~2.266 unplaceable
        folders sat in the import folder on production: every cycle re-read all of them
        to arrive at the same answer. The proposal row stores a fingerprint of what the
        folder was resolved against -- its entries, size and newest mtime, the
        catalogue-number rules, and the row's own decision -- and the tags are read
        again only when that fingerprint no longer matches. Stored in the database, so
        a restart or a deploy does not start the whole backlog over.

        `warning` is logged only when the folder is actually resolved, i.e. the first
        time and after a change: repeating it every cycle for thousands of folders is
        what the per-cycle count in `run` replaces.
        """
        self._counts['checked'] += 1
        src = join(self.settings.import_folder_path, folder)
        signature = folder_signature(src)
        snapshot = self._snapshot
        expected = None
        if signature is not None and snapshot is not None:
            row = snapshot.rows.get(folder, NEW_ROW)
            expected = fingerprint(signature, snapshot.rules_version, row)
            if row.fingerprint == expected:
                self._counts['skipped'] += 1
                return
        elif signature is not None and self._resolved.get(folder) == signature:
            # No database to compare with: fall back to what this process remembers.
            self._counts['skipped'] += 1
            return
        logging.warning(warning)
        import_folder_name = os.path.basename(self.settings.import_folder_path.rstrip(os.sep))
        self.proposals.record(
            folder,
            resolve(src, import_folder_name=import_folder_name, catid_from_name=cat_id or None),
            expected,
        )
        self._counts['reread'] += 1
        if signature is not None:
            self._resolved[folder] = signature

    def get_label(self, key) -> str | None:
        query = 'SELECT `label` FROM `rules_catid_label` WHERE `catid` = %s'
        try:
            with self.db_connector.connection() as connection, connection.cursor() as cursor:
                cursor.execute(query, key)
                result = cursor.fetchone()
                if result:
                    return str(result[0])
                return None
        except Exception as e:
            logging.error(f'Error querying database: {e}')
            return None

    def remove(self, folder):
        """Park a source folder this step decided not to keep.

        Named `remove` because that is what it meant, and it is called from the two places
        that judge a folder to be a duplicate download. The judgement rests on
        `is_same_release`, which compares track names and lengths rather than contents, so
        it can be wrong -- and it used to be wrong irreversibly. Quarantine.sweep does the
        actual deleting, once the retention window has closed.
        """
        src = join(self.settings.import_folder_path, folder)
        if Quarantine.put(src, Quarantine.DUPLICATE_RELEASE):
            return
        # Nowhere to park it. Leaving the folder in the import queue means this cycle logs
        # the conflict again next time, which is noisy and recoverable; deleting it is not.
        logging.warning('Could not quarantine %s; leaving it in the import folder', src)

    def _resolve_conflict(self, folder, src, dst, dry_run):
        """Decides what to do when the label folder already holds this release.

        Same rule as the renamer: the same track names and lengths mean the release was
        imported before and this is a duplicate download, so the source goes. Anything
        else may be a different release that resolved to the same folder name, and gets
        left alone rather than merged into the one already there -- warned about once,
        then counted in the cycle's summary line until someone resolves it (bug 091).
        """
        if self.conflicts.unchanged(src, dst):
            return
        if not is_same_release(src, dst):
            self.conflicts.differs(src, dst, dry_run=dry_run)
            return
        self.conflicts.same(src, dst)
        logging.warning('Conflict: %s already exists and holds the same files. Removing %s', dst, src)
        if not dry_run:
            self.remove(folder)

    def _move_folder(self, folder, cat_id, dry_run):
        """Processes and moves a single folder based on its CAT ID."""
        label = self.get_label(cat_id)
        if label is None:
            if self._place(folder, dry_run):
                return
            error_msg = (
                f'CAT ID {cat_id} not found in database for folder {folder}. Please add it to rules_catid_label.'
            )
            self._propose(folder, cat_id, error_msg)
            return
        self._move_to_label(folder, label, dry_run)

    def _move_to_label(self, folder, label, dry_run, placement: Placement | None = None):
        """Moves one release folder into `label`'s folder and tags it there."""
        src = join(self.settings.import_folder_path, folder)
        dst = join(self.settings.eps_folder_path, label, folder)
        # Checked before the move, not after it, because shutil.move does not fail on an
        # existing destination directory -- it moves *into* it, so a second copy of a
        # release ends up at dst/<same name>/, one level deeper, and stays there. The
        # exception branch below only fires on the third copy, once that nested folder
        # exists too. 429 release folders on production contained themselves this way.
        if os.path.exists(dst):
            self._resolve_conflict(folder, src, dst, dry_run)
            return
        # Before the move, while the .nfo is still where the cache knows it: the store's
        # answer is what the tagging pass below reads the release date from.
        try:
            self.release_info.album(src, self._budget)
        except Exception as e:  # noqa: BLE001 - the date ladder falls back on the .nfo
            logging.info(f'No store lookup for {folder}: {e}')
        arrival = self._arrival(folder)
        backlog = self._is_backlog(folder)
        try:
            if not dry_run:
                shutil.move(src, dst)
                logging.info(f'Successfully moved: {src} -> {dst}')
                # Before the tagging pass below, which is the first thing that writes to
                # these files. It runs as root and would succeed either way; everything
                # after it, and everyone reaching the share over SMB, would not.
                make_library_writable(dst)
                # Both paths: the new one so LMS reads the files, the old one so the rows
                # underneath a folder that is now gone get removed.
                lms_scan_trigger.notify([src, dst])
            else:
                logging.info(f'Dry run - would move: {src} -> {dst}')
            try:
                tracks = post_processing_songs(dst, arrival_date=arrival)
            except Exception as e:
                logging.error(f'Post-processing failed for {dst}: {e}')
            else:
                if not dry_run:
                    # A release that already waited as unplaceable is backlog: placing a few
                    # thousand of those after a rule or this feature lands must not become as
                    # many phone pushes. The event is still written.
                    notification_service.notify(
                        release_summary(folder, label, tracks, placement), title='Import Complete', push=not backlog
                    )
        except (FileExistsError, shutil.Error) as e:
            # shutil.move(src, dst) treats an existing "dst" directory as a target to move
            # INTO (i.e. src ends up at dst/basename(src)), not as an in-place conflict. If
            # that folder (from a previous successful import of the same release) already
            # exists too, shutil.move raises shutil.Error (a subclass of OSError on modern
            # Python, so it used to be silently swallowed by the generic "except OSError"
            # branch below as a bogus "check disk space/filesystem" error) instead of
            # FileExistsError. Either way the release was already imported previously, so
            # the conflicting leftover source folder has to stop being retried (and
            # re-logged as an error) on every single import cycle forever.
            #
            # Routed through the same comparison `_resolve_conflict` makes rather than
            # acting on the exception alone. Both branches answer the same question --
            # "is what is already at dst this release?" -- and only one of them used to
            # ask it: this one removed the source on the exception alone, so a genuinely
            # different release that raced into the same destination was discarded without
            # anything ever looking at it.
            #
            # Since the `os.path.exists(dst)` check above, that race is the only way to
            # get here: dst was not there when it was checked and is there now, which
            # means another cycle placed it in between. So dst holds a complete release
            # and comparing src against it is exactly the right question.
            logging.warning('Conflict: %s already exists (%s)', dst, e)
            self._resolve_conflict(folder, src, dst, dry_run)
        except PermissionError as e:
            logging.error(f'Permission denied when moving {src} to {dst}: {e}')
        except OSError as e:
            logging.error(f'OS error when moving {src} to {dst} (check disk space/filesystem): {e}')
        except Exception as e:
            logging.error(f'Unexpected error moving {src} to {dst}: {e}')

    def run(self, dry_run=False):
        """
        Move folders to categorized destinations based on their library_labels.
        """
        logging.info('Starting Move Step')
        self._snapshot = self.proposals.snapshot()
        self._counts = {'checked': 0, 'skipped': 0, 'reread': 0}
        self._begin_release_info_cycle()
        self.conflicts.begin()
        only_folders = [
            f
            for f in listdir(self.settings.import_folder_path)
            if not isfile(join(self.settings.import_folder_path, f)) and not is_staging(f)
        ]
        for folder in only_folders:
            # A release still being copied in would be moved with half its tracks, and
            # the rest would arrive in a new import folder the next cycle calls a conflict.
            if not is_settled(join(self.settings.import_folder_path, folder)):
                continue
            cat_id = get_cat_id(folder)
            if cat_id:
                self._move_folder(folder, cat_id, dry_run)
            elif not self._place(folder, dry_run):
                error_msg = f'No valid CAT ID found for folder: {folder}. Manual intervention required.'
                self._propose(folder, None, error_msg)
        logging.info(
            'Unplaceable folders: %d checked, %d skipped as unchanged, %d re-read',
            self._counts['checked'],
            self._counts['skipped'],
            self._counts['reread'],
        )
        self.conflicts.end(dry_run=dry_run)
