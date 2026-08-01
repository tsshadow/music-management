"""Interactive repair for EP folders that sit one directory too deep.

Some EPs were downloaded twice and ended up as

    /mnt/music/EPs/<Label>/<EP folder>/<EP folder>/*.mp3

Because LabelSong derives Publisher/Catalog from the folder structure, the files in the
inner directory are tagged with a label of `<CAT ID>-<EP name>` instead of the real label
name, which pollutes the label lists. This script finds those folders, asks what to do with
each one, moves or deletes on confirmation, and drops the stale rows from the database so
the scanner re-adds the files at their new path.

Run it by hand:

    python -m tools.fix_nested_ep_dirs [--label "Sealand Recordings"] [--dry-run]
"""
import argparse
import hashlib
import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

from services.common.Helpers.DatabaseConnector import DatabaseConnector

load_dotenv()

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.aac', '.wav')
IGNORED_DIRS = ('@eaDir',)

MOVE_UP = 'MOVE_UP'
DELETE_DUP = 'DELETE_DUP'
PARTIAL = 'PARTIAL'

MANUAL = """
================================================================================
 fix_nested_ep_dirs - repair EP folders that are one directory too deep
================================================================================

WHAT IT LOOKS FOR
  <eps root>/<Label>/<EP folder>/<EP folder>/   - an inner directory whose name is
  exactly equal to its parent. That is the double-download case; the files inside it
  get the catalog folder as their label tag instead of the real label name.

  Subfolders with a *different* name are never touched. They are collected in the
  report at the end so you can look at them yourself.

WHAT EACH CASE MEANS
  MOVE_UP      the outer folder holds no audio -> the inner files belong one level up
  DELETE_DUP   the outer folder already holds every file the inner one has
  PARTIAL      the outer folder has audio, but the inner one holds files it lacks

WHAT YOU CAN ANSWER
  y   move the inner files up, then remove the emptied inner folder   (MOVE_UP)
  d   delete the inner folder and everything in it                    (DELETE_DUP, PARTIAL)
  m   move only the inner-only files up, then delete the rest         (PARTIAL)
  s   skip this case, change nothing
  q   quit; everything already handled stays handled

RULES
  Scanning the whole music mount takes minutes. Every hit is printed under its label
  while the scan runs, so use --label to look at one label straight away.
  Nothing is written before you press a key. Existing files are never overwritten: a
  name clash leaves that file where it is and keeps the inner folder alive. Every path
  that disappears from disk is removed from library_media_files,
  library_track_audio_features and tagger_processed_files, and one LMS scan is
  triggered at the end so the library picks the files up at their new location.
================================================================================
"""


def list_files(path: str) -> List[str]:
    """File names directly inside `path`, ignoring subdirectories and @eaDir."""
    try:
        entries = os.scandir(path)
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return []
    with entries:
        return sorted(entry.name for entry in entries if entry.is_file())


def list_dirs(path: str) -> List[str]:
    """Subdirectory names directly inside `path`, ignoring @eaDir."""
    try:
        entries = os.scandir(path)
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return []
    with entries:
        return sorted(entry.name for entry in entries if entry.is_dir() and entry.name not in IGNORED_DIRS)


def is_audio(name: str) -> bool:
    return name.lower().endswith(AUDIO_EXTENSIONS)


def has_audio(names: Sequence[str]) -> bool:
    return any(is_audio(name) for name in names)


def walk_files(path: str) -> List[str]:
    """Every real file under `path`, recursively, ignoring @eaDir."""
    found = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        found.extend(os.path.join(root, name) for name in sorted(files))
    return found


def relative_files(path: str) -> List[str]:
    """Every real file under `path` as a path relative to it.

    Recursive on purpose: a file hiding in a subdirectory must show up in the listing and
    in the comparison, otherwise a folder that looks empty could be deleted with audio
    still in it.
    """
    return sorted(os.path.relpath(found, path) for found in walk_files(path))


@dataclass
class Case:
    outer: str
    inner: str
    outer_files: List[str]
    inner_files: List[str]
    action: str

    @property
    def unique_inner_files(self) -> List[str]:
        outer = set(self.outer_files)
        return [name for name in self.inner_files if name not in outer]

    def describe(self) -> str:
        unique = set(self.unique_inner_files)
        outer_lines = '\n'.join(f'    {name}' for name in self.outer_files) or '    (none)'
        inner_lines = '\n'.join(
            f'  {"*" if name in unique else " "} {name}' for name in self.inner_files
        ) or '    (none)'
        return (
            f'\n{"-" * 78}\n'
            f'{self.action}  {self.outer}\n'
            f'  outer folder holds:\n{outer_lines}\n'
            f'  inner folder ({os.path.basename(self.inner)}) holds:   (* = not present above)\n{inner_lines}\n'
        )


@dataclass
class Result:
    moved: List[str] = field(default_factory=list)
    clashes: List[str] = field(default_factory=list)
    vanished: List[str] = field(default_factory=list)
    inner_removed: bool = False
    db_deleted: int = 0

    @property
    def db_failed(self) -> bool:
        return self.db_deleted < 0


def classify(outer: str, inner: str) -> Case:
    inner_name = os.path.basename(inner)
    outer_files = [name for name in relative_files(outer) if not name.startswith(inner_name + os.sep)]
    inner_files = relative_files(inner)
    if not has_audio(outer_files):
        action = MOVE_UP
    elif set(inner_files) <= set(outer_files):
        action = DELETE_DUP
    else:
        action = PARTIAL
    return Case(outer=outer, inner=inner, outer_files=outer_files, inner_files=inner_files, action=action)


def find_cases(
    eps_root: str,
    label: Optional[str] = None,
    on_progress: Optional[Callable[[str], None]] = None,
    on_case: Optional[Callable[[Case], None]] = None,
) -> Tuple[List[Case], List[str]]:
    """Scan the EPs tree for inner directories named exactly like their parent.

    Returns the cases plus a list of oddities: differently named subdirectories that this
    script refuses to touch. `on_case` is called for every hit the moment it is found:
    walking the whole music mount takes minutes, and a run that shows nothing until the
    end looks like it found nothing.
    """
    cases: List[Case] = []
    oddities: List[str] = []
    labels = [label] if label else list_dirs(eps_root)
    for label_name in labels:
        label_path = os.path.join(eps_root, label_name)
        if on_progress:
            on_progress(label_name)
        for ep_name in list_dirs(label_path):
            ep_path = os.path.join(label_path, ep_name)
            for sub_name in list_dirs(ep_path):
                sub_path = os.path.join(ep_path, sub_name)
                if sub_name == ep_name:
                    case = classify(ep_path, sub_path)
                    cases.append(case)
                    if on_case:
                        on_case(case)
                else:
                    oddities.append(sub_path)
    return cases, oddities


class DbCleaner:
    """Removes rows for file paths that no longer exist on disk."""

    def __init__(self) -> None:
        self.db_connector = DatabaseConnector()

    @staticmethod
    def path_hash(path: str) -> str:
        """Same hash the scanner stores in library_media_files.file_path_hash."""
        return hashlib.sha256(path.encode('utf-8')).hexdigest()

    def delete_paths(self, paths: Sequence[str]) -> int:
        """Returns the number of library_media_files rows deleted, or -1 on failure."""
        if not paths:
            return 0
        deleted = 0
        try:
            connection = self.db_connector.connect()
        except Exception as error:
            # The files are already moved at this point; losing the database cleanup is
            # recoverable (a rescan fixes it), crashing halfway through a run is not.
            logging.error('Could not connect to the database, rows left behind: %s', error)
            return -1
        try:
            with connection.cursor() as cursor:
                for path in paths:
                    cursor.execute(
                        'DELETE FROM library_media_files WHERE file_path_hash = %s',
                        (self.path_hash(path),),
                    )
                    deleted += cursor.rowcount or 0
                    cursor.execute(
                        'DELETE FROM library_track_audio_features WHERE file_path = %s',
                        (path,),
                    )
                    cursor.execute(
                        'DELETE FROM tagger_processed_files WHERE filepath = %s',
                        (path,),
                    )
            connection.commit()
        except Exception as error:
            logging.error('Database cleanup failed: %s', error)
            connection.rollback()
            deleted = -1
        finally:
            connection.close()
        return deleted


class Executor:
    """Performs the filesystem changes and the matching database cleanup."""

    def __init__(self, db: DbCleaner, dry_run: bool = False) -> None:
        self.db = db
        self.dry_run = dry_run

    def move_up(self, case: Case) -> Result:
        """Move every inner file one level up, skipping name clashes."""
        return self._move(case, case.inner_files, delete_rest=False)

    def merge_unique(self, case: Case) -> Result:
        """Move only the inner-only files up, then delete whatever is left."""
        return self._move(case, case.unique_inner_files, delete_rest=True)

    def delete_inner(self, case: Case) -> Result:
        result = Result()
        before = walk_files(case.inner)
        if self.dry_run:
            return result
        shutil.rmtree(case.inner, ignore_errors=True)
        result.inner_removed = not os.path.exists(case.inner)
        result.vanished = self._vanished(before)
        result.db_deleted = self.db.delete_paths(result.vanished)
        return result

    def _move(self, case: Case, names: Sequence[str], delete_rest: bool) -> Result:
        result = Result()
        before = walk_files(case.inner)
        if self.dry_run:
            result.clashes = [name for name in names if os.path.exists(os.path.join(case.outer, name))]
            return result
        for name in names:
            source = os.path.join(case.inner, name)
            target = os.path.join(case.outer, name)
            if os.path.exists(target):
                result.clashes.append(name)
                continue
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.move(source, target)
                result.moved.append(target)
            except OSError as error:
                logging.error('Could not move %s: %s', source, error)
                result.clashes.append(name)
        if not result.clashes and (delete_rest or not walk_files(case.inner)):
            shutil.rmtree(case.inner, ignore_errors=True)
        result.inner_removed = not os.path.exists(case.inner)
        result.vanished = self._vanished(before)
        result.db_deleted = self.db.delete_paths(result.vanished)
        return result

    @staticmethod
    def _vanished(paths: Sequence[str]) -> List[str]:
        return [path for path in paths if not os.path.exists(path)]


PROMPTS = {
    MOVE_UP: ('ys', '  [y] move inner files up + remove inner folder   [s] skip   [q] quit: '),
    DELETE_DUP: ('ds', '  [d] delete inner folder   [s] skip   [q] quit: '),
    PARTIAL: ('mds', '  [m] merge inner-only files up   [d] delete inner folder   [s] skip   [q] quit: '),
}


def ask(case: Case, read: Callable[[str], str] = input) -> str:
    allowed, prompt = PROMPTS[case.action]
    while True:
        answer = read(prompt).strip().lower()
        if answer == 'q' or answer in allowed:
            return answer
        print(f'  Please answer one of: {", ".join(allowed)}, q')


def resolve_eps_root(override: Optional[str]) -> str:
    if override:
        return override
    try:
        from services.common.config_store import ConfigStore
        configured = ConfigStore().get('eps_folder_path')
        if configured:
            return str(configured)
    except Exception as error:
        logging.debug('Could not read eps_folder_path from config: %s', error)
    return os.getenv('EPS_PATH', '/mnt/music/EPs')


def trigger_lms_scan() -> None:
    """Best effort: the trigger helper is not present in every checkout."""
    try:
        from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
    except ImportError:
        print('LMS scan trigger not available in this checkout - trigger a scan yourself.')
        return
    lms_scan_trigger.trigger()
    print('LMS scan triggered.')


def write_report(path: str, lines: Sequence[str]) -> None:
    with open(path, 'w') as handle:
        handle.write('\n'.join(lines) + '\n')
    print(f'Report written to {path}')


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Repair EP folders that are one directory too deep.')
    parser.add_argument('--eps-root', help='EPs root directory (default: eps_folder_path from config)')
    parser.add_argument('--label', help='Only scan this label directory (the music mount is slow)')
    parser.add_argument('--dry-run', action='store_true', help='Classify and print, change nothing')
    parser.add_argument('--report', default='fix_nested_ep_dirs_report.txt', help='Where to write the report')
    args = parser.parse_args(argv)

    print(MANUAL)
    eps_root = resolve_eps_root(args.eps_root)
    if not os.path.isdir(eps_root):
        print(f'EPs root does not exist: {eps_root}')
        return 1
    print(f'Scanning {eps_root}' + (f' (label: {args.label})' if args.label else '') + ' ...')

    cases, oddities = find_cases(
        eps_root,
        args.label,
        on_progress=lambda name: print(f'  {name}', flush=True),
        on_case=lambda case: print(f'    -> {case.action}  {os.path.basename(case.outer)}', flush=True),
    )
    print(f'\nFound {len(cases)} nested EP folder(s), {len(oddities)} differently named subfolder(s).')
    if not cases and not oddities:
        return 0

    report = [f'Differently named subfolder (not touched): {path}' for path in oddities]
    executor = Executor(DbCleaner(), dry_run=args.dry_run)
    handled = {'moved': 0, 'deleted': 0, 'skipped': 0}

    for case in cases:
        print(case.describe())
        if args.dry_run:
            handled['skipped'] += 1
            continue
        answer = ask(case)
        if answer == 'q':
            print('Quitting.')
            break
        if answer == 's':
            handled['skipped'] += 1
            report.append(f'Skipped: {case.inner}')
            continue
        if answer == 'y':
            result = executor.move_up(case)
        elif answer == 'm':
            result = executor.merge_unique(case)
        else:
            result = executor.delete_inner(case)
        if answer in ('y', 'm'):
            handled['moved'] += 1
            print(f'  moved {len(result.moved)} file(s), {len(result.vanished)} path(s) gone from disk')
        else:
            handled['deleted'] += 1
            print(f'  deleted inner folder, {len(result.vanished)} path(s) gone from disk')
        if result.db_failed:
            print('  database cleanup FAILED for this folder - see the error above')
            report.append(f'Database cleanup failed, stale rows remain: {case.inner}')
        elif result.vanished:
            print(f'  database: {result.db_deleted} media file row(s) removed')
        if result.clashes:
            print(f'  name clash, left in place: {", ".join(result.clashes)}')
            report.append(f'Name clash, inner folder kept: {case.inner} ({", ".join(result.clashes)})')
        elif not result.inner_removed:
            report.append(f'Inner folder could not be removed: {case.inner}')

    print(
        f"\nDone. moved: {handled['moved']}, deleted: {handled['deleted']}, "
        f"skipped: {handled['skipped']}."
    )
    if report:
        write_report(args.report, report)
    if not args.dry_run and (handled['moved'] or handled['deleted']):
        trigger_lms_scan()
    return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    sys.exit(main())
