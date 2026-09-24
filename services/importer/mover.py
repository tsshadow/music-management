import logging
import os
import re
import shutil
from os import listdir
from os.path import isfile, join

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers import Quarantine
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.common.Helpers.NotificationService import notification_service
from services.importer.label_proposal_store import LabelProposalStore
from services.importer.label_resolver import resolve
from services.importer.release_compare import is_same_release
from services.importer.settle import is_settled, is_staging, newest_mtime
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


def post_processing_songs(folder_path) -> int:
    """
    Call LabelSong(path) for every supported audio file in the folder,
    excluding Synology's @eaDir directories and non-files.

    Every tagged file is recorded in the event log, without a push: one per file was
    100+ phone notifications for a single weekly pack. The mover sends one push per
    release instead, which is why this returns how many files were tagged.
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
                    s.parse()
                    # The walk would otherwise tag the release a second time on its next
                    # pass; and the scanner learns of it now rather than on the hour.
                    announce(full_path)
                    notification_service.notify(str(s), title='Track Imported', push=False)
                    tagged += 1
                except Exception as e:
                    logging.error(f'Failed to process {full_path} with LabelSong: {e}')
    return tagged


def release_summary(folder: str, label: str, tracks: int) -> str:
    """The one push a release gets: label, catalogue number and how many tracks were imported.

    The catalogue number is the part of the folder name before the renamer's ` - `, which
    is the full number (`SCAN123`) rather than the prefix the label was looked up by.
    """
    catalog = folder.split(' - ', 1)[0].strip() if ' - ' in folder else ''
    lines = [folder, f'Label: {label}']
    if catalog:
        lines.append(f'Catalog: {catalog}')
    lines.append(f'Tracks: {tracks}')
    return '\n'.join(lines)


class Mover:
    """Moves every settled release folder in the import folder to its label, and tags it there."""

    def __init__(self):
        self.settings = Settings()
        self.db_connector = DatabaseConnector()
        self.proposals = LabelProposalStore()
        #: folder -> newest modification time inside it when its label was last resolved.
        #: Lives as long as the process, which runs the import loop for weeks.
        self._resolved: dict[str, float] = {}

    def _propose(self, folder, cat_id):
        """
        Record a release this step could not place, so it can be reviewed once instead
        of re-warned on every cycle for as long as it sits in the import folder.

        Resolving reads the tags of every track, over CIFS, and ~2.266 unplaceable
        folders sat in the import folder on production: every cycle re-read all of them
        to arrive at the same answer. A folder is resolved again only when something in
        it changed since the last time this process resolved it. A decision on the
        proposal does not depend on this: confirming one with a catalogue number adds
        the `rules_catid_label` row the lookup before this finds, and confirming one
        without moves the folder itself.
        """
        src = join(self.settings.import_folder_path, folder)
        try:
            changed = newest_mtime(src)
        except OSError as e:
            logging.debug('Could not read %s to decide whether to resolve it again: %s', src, e)
            changed = None
        if changed is not None and self._resolved.get(folder) == changed:
            logging.debug('Label proposal for %s is current; not reading its tags again', folder)
            return
        import_folder_name = os.path.basename(self.settings.import_folder_path.rstrip(os.sep))
        self.proposals.record(
            folder, resolve(src, import_folder_name=import_folder_name, catid_from_name=cat_id or None)
        )
        if changed is not None:
            self._resolved[folder] = changed

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
        left alone rather than merged into the one already there.
        """
        if not is_same_release(src, dst):
            logging.warning(
                'Conflict: %s already exists but its contents differ from %s. '
                'Leaving both in place for manual intervention',
                dst,
                src,
            )
            return
        logging.warning('Conflict: %s already exists and holds the same files. Removing %s', dst, src)
        if not dry_run:
            self.remove(folder)

    def _move_folder(self, folder, cat_id, dry_run):
        """Processes and moves a single folder based on its CAT ID."""
        label = self.get_label(cat_id)
        if label is None:
            error_msg = (
                f'CAT ID {cat_id} not found in database for folder {folder}. Please add it to rules_catid_label.'
            )
            logging.warning(error_msg)
            self._propose(folder, cat_id)
            return
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
                tracks = post_processing_songs(dst)
            except Exception as e:
                logging.error(f'Post-processing failed for {dst}: {e}')
            else:
                if not dry_run:
                    notification_service.notify(release_summary(folder, label, tracks), title='Import Complete')
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
            else:
                error_msg = f'No valid CAT ID found for folder: {folder}. Manual intervention required.'
                logging.warning(error_msg)
                self._propose(folder, None)
