"""Gives release folders in the label tree back the name the old Renamer took from them.

`prefix_strip_repair` does this for the import queue. The same misnamed folders also reached the
label tree before bug report 145, because a rule or a person moved them there by hand:
`EPs/B2S/Official_Hardbass_2026_Anthem - Minus_Militia_And_Nolz_-_Recover_The_Archive_(...)`.
The tagger then reads `Official_Hardbass_2026_Anthem` from the path as the catalogue number and
writes it into every file of the release.

The planner walks `<eps root>/<label>/<release>` for every folder `ImportQueue.is_label_folder`
accepts, so the queue and the `_` folders (`__Free&None`) are never touched. A release folder
named `<prefix> - <rest>` is one of three kinds:

* the prefix passes `catalogue_number.rejection`: a real catalogue number, left alone and not
  listed;
* the prefix is refused, it is exactly what the old Renamer took from `<rest>`, and no
  `rules_catid_label` rule routes it: RENAME, to `<catalogue number> - <rest>` when the rest
  carries one, else to the bare `<rest>` (what the Renamer writes today), or ` - <rest>` when
  the rest holds a space, so the tagger cannot read a word in front of it as a number;
* the prefix holds no digit: a label code a person typed (`FILTHY`, `MOHDIGI`). The old Renamer
  only took a group with a digit in it, so it is left alone and not listed;
* the prefix holds a digit and is refused, but the old Renamer cannot have produced it from the
  rest, or a rule routes it: AMBIGUOUS. Listed, never renamed: a person decides
  (`I_Am_Frenchcore_05`).

An empty prefix (` - <release>`) means "no catalogue number" in the label tree and is fine.

For every rename, in this order and inside one database transaction:

  1. the stored paths of the release's files move with it: `library_media_files.file_path` and
     its `file_path_hash`, and `tagger_processed_files.filepath`, the way
     `move-import-queue.sh` moves them. The track rows keep their ids, and
     ratings key on `track_uid`, so nothing a listener made is lost;
  2. the folder is renamed;
  3. the commit. A failed commit renames the folder back.

Then the `CATALOGNUMBER` tag of each audio file in the release is removed when it holds exactly
the word prefix, because the tagger only writes a catalogue number it finds and never clears
one. Other tags, the publisher among them, are not touched: the folder above stays the label.
LMS is told about both paths. Each rename is logged as one JSON line before the next starts.

    python -m services.importer.label_tree_prefix_repair --dry-run [--json plan.json]
    python -m services.importer.label_tree_prefix_repair --backup-where media|tagger
    python -m services.importer.label_tree_prefix_repair --apply --log /tmp/label-tree.jsonl
    python -m services.importer.label_tree_prefix_repair --rollback /tmp/label-tree.jsonl

`repair-word-prefixed-import-folders.sh --label-tree` wraps it.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from services.common.catalogue_number import from_folder_name, old_rule_prefix, rejection
from services.importer import catid_prefix_repair as base
from services.importer.prefix_strip_repair import EMPTY_PREFIXES

#: The tag the tagger writes the catalogue number to, as each format spells its key once the
#: frame or atom prefix is cut off and the rest is upper-cased.
CATALOGUE_TAG = 'CATALOGNUMBER'

_ID3_PREFIX = 'TXXX:'
_MP4_PREFIX = '----:com.apple.iTunes:'
AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.wav', '.opus')

# `<prefix> - <rest>`, the prefix without whitespace: the shape the old Renamer wrote.
_PREFIXED = re.compile(r'^(\S+) - (.*)$', re.S)


@dataclass(frozen=True)
class LabelRename:
    """One word-prefixed release folder in the label tree and what the planner does with it.

    `verdict` is `rename`, `ambiguous` (listed for a person) or `skip` (a rename onto a name
    already taken). `new` is set only for `rename`.
    """

    label: str
    old: str
    new: str | None
    prefix: str
    verdict: str
    reason: str

    @property
    def old_path(self) -> str:
        """The folder relative to the EPs root: `<label>/<old name>`."""
        return f'{self.label}/{self.old}'

    @property
    def new_path(self) -> str | None:
        """The renamed folder relative to the EPs root, when it is renamed."""
        return f'{self.label}/{self.new}' if self.new else None


def target_name(rest: str) -> str:
    """The name a release folder gets once its word prefix is gone."""
    catalogue_number = from_folder_name(rest)
    if catalogue_number:
        return f'{catalogue_number} - {rest}'
    return f' - {rest}' if ' ' in rest else rest


def classify(label: str, name: str, rules: dict[str, str]) -> LabelRename | None:
    """What to do with one release folder, or None when its prefix is no problem.

    `rules` maps a lowercased `rules_catid_label` prefix to its label.
    """
    if name.startswith(EMPTY_PREFIXES):
        return None
    match = _PREFIXED.match(name)
    if not match:
        return None
    prefix, rest = match.groups()
    why = rejection(prefix)
    if why is None:
        return None
    if not any(char.isdigit() for char in prefix):
        # The old Renamer only took a group holding a digit: a person typed this (`FILTHY`).
        return None
    if old_rule_prefix(rest) != prefix:
        return LabelRename(label, name, None, prefix, 'ambiguous', f'not what the old Renamer took ({why})')
    rule_key = base.rule_prefix(prefix).lower()
    if rule_key and rule_key in rules:
        return LabelRename(label, name, None, prefix, 'ambiguous', f'a rule routes it to {rules[rule_key]} ({why})')
    return LabelRename(label, name, target_name(rest), prefix, 'rename', f'word prefix ({why})')


def plan(folders: Iterable[tuple[str, str]], rules: dict[str, str]) -> list[LabelRename]:
    """Plans every word-prefixed `(label, release)` folder, refusing a rename onto a taken name."""
    existing = set(folders)
    taken: set[tuple[str, str]] = set()
    planned: list[LabelRename] = []
    for label, name in sorted(existing):
        entry = classify(label, name, rules)
        if entry is None:
            continue
        if entry.new is not None:
            target = (label, entry.new)
            if target in existing or target in taken:
                entry = LabelRename(label, name, None, entry.prefix, 'skip', f'target exists: {entry.new}')
            else:
                taken.add(target)
        planned.append(entry)
    return planned


def summarize(planned: list[LabelRename], scanned: int) -> dict:
    """Counts for a plan: folders looked at, renames, ambiguous and refused folders."""
    return {
        'release_folders': scanned,
        'word_prefixed': len(planned),
        'renameable': sum(1 for entry in planned if entry.verdict == 'rename'),
        'ambiguous': sum(1 for entry in planned if entry.verdict == 'ambiguous'),
        'target_exists': sum(1 for entry in planned if entry.verdict == 'skip'),
    }


def label_tree_folders(eps_root: str, queue) -> list[tuple[str, str]]:
    """Every `(label, release)` directory pair under the label folders `queue` accepts."""
    found: list[tuple[str, str]] = []
    for label in sorted(os.listdir(eps_root)):
        label_path = os.path.join(eps_root, label)
        if not os.path.isdir(label_path) or not queue.is_label_folder(label_path):
            continue
        for name in os.listdir(label_path):
            if os.path.isdir(os.path.join(label_path, name)):
                found.append((label, name))
    return found


def _sql_text(value: str) -> str:
    """`value` as a MariaDB string literal."""
    return "'" + value.replace('\\', '\\\\').replace("'", "''") + "'"


def backup_where(planned: list[LabelRename], eps_root: str, column: str) -> str:
    """A `--where` for mariadb-dump that selects the rows of every folder about to be renamed."""
    clauses = []
    for entry in planned:
        if entry.verdict != 'rename':
            continue
        folder = _sql_text(os.path.join(eps_root, entry.old_path) + '/')
        clauses.append(f'LEFT({column}, CHAR_LENGTH({folder})) = {folder}')
    return ' OR '.join(clauses) or '1 = 0'


# ---------------------------------------------------------------------------- side effects


def rewrite_paths(cursor, old_dir: str, new_dir: str) -> tuple[int, int]:
    """Moves the stored paths below `old_dir` to `new_dir`. Returns (media rows, tagger rows)."""
    old = old_dir.rstrip('/') + '/'
    new = new_dir.rstrip('/') + '/'
    cursor.execute(
        'UPDATE library_media_files '
        'SET file_path = CONCAT(%s, SUBSTRING(file_path, CHAR_LENGTH(%s) + 1)), '
        'file_path_hash = SHA2(CONCAT(%s, SUBSTRING(file_path, CHAR_LENGTH(%s) + 1)), 256) '
        'WHERE LEFT(file_path, CHAR_LENGTH(%s)) = %s',
        (new, old, new, old, old, old),
    )
    media = cursor.rowcount or 0
    cursor.execute(
        'UPDATE tagger_processed_files SET filepath = CONCAT(%s, SUBSTRING(filepath, CHAR_LENGTH(%s) + 1)) '
        'WHERE LEFT(filepath, CHAR_LENGTH(%s)) = %s',
        (new, old, old, old),
    )
    return media, cursor.rowcount or 0


def _tag_values(value) -> list[str]:
    """The text of one tag value, whatever the format wraps it in."""
    items = value if isinstance(value, list) else getattr(value, 'text', [value])
    texts = []
    for item in items:
        if isinstance(item, bytes):
            item = item.decode('utf-8', 'replace')
        texts.append(str(item))
    return texts


def _catalogue_keys(tags, prefix: str) -> list[str]:
    """The keys of `tags` that hold exactly `prefix` as the catalogue number."""
    keys = []
    for key in list(tags.keys()):
        name = str(key)
        for frame in (_ID3_PREFIX, _MP4_PREFIX):
            if name.startswith(frame):
                name = name[len(frame) :]
        if name.upper() == CATALOGUE_TAG and _tag_values(tags[key]) == [prefix]:
            keys.append(key)
    return keys


def drop_catalogue_tag(path: str, prefix: str, open_file: Callable | None = None) -> bool:
    """Removes the catalogue-number tag of one file when it holds exactly `prefix`."""
    if open_file is None:
        from mutagen import File  # pylint: disable=import-outside-toplevel

        open_file = File
    audio = open_file(path)
    tags = getattr(audio, 'tags', None) if audio is not None else None
    if tags is None:
        return False
    keys = _catalogue_keys(tags, prefix)
    if not keys:
        return False
    for key in keys:
        del tags[key]
    audio.save()
    return True


def drop_catalogue_tags(folder: str, prefix: str, drop: Callable[[str, str], bool] = drop_catalogue_tag) -> int:
    """Removes the word catalogue number from every audio file below `folder`. Returns the count."""
    dropped = 0
    for directory, _, files in os.walk(folder):
        for name in sorted(files):
            if not name.lower().endswith(AUDIO_EXTENSIONS):
                continue
            try:
                dropped += 1 if drop(os.path.join(directory, name), prefix) else 0
            except Exception as error:  # pylint: disable=broad-except
                # The rename is done and logged; a file mutagen cannot write keeps its tag.
                logging.warning('could not clear the catalogue number of %s: %s', name, error)
    return dropped


def _move(connection, src: str, dst: str, rename: Callable[[str, str], None]) -> tuple[int, int]:
    """Rewrites the stored paths and renames the folder as one unit; undone together on failure."""
    try:
        with connection.cursor() as cursor:
            rows = rewrite_paths(cursor, src, dst)
        rename(src, dst)
    except Exception:
        connection.rollback()
        raise
    try:
        connection.commit()
    except Exception:
        rename(dst, src)
        raise
    return rows


def apply_plan(
    planned: list[LabelRename],
    eps_root: str,
    log_path: str,
    connection,
    rename: Callable[[str, str], None] = os.rename,
    notify: Callable[[list[str]], None] | None = None,
    drop: Callable[[str, str], bool] = drop_catalogue_tag,
) -> dict:
    """Renames every planned folder, logging each one before the next starts."""
    done = skipped = media = tagger = tags = 0
    with open(log_path, 'a', encoding='utf-8') as log:
        for entry in planned:
            if entry.verdict != 'rename' or not entry.new_path:
                continue
            src = os.path.join(eps_root, entry.old_path)
            dst = os.path.join(eps_root, entry.new_path)
            if not os.path.isdir(src) or os.path.exists(dst):
                skipped += 1
                continue
            rows = _move(connection, src, dst, rename)
            cleared = drop_catalogue_tags(dst, entry.prefix, drop)
            record = {
                'label': entry.label,
                'old': entry.old,
                'new': entry.new,
                'media_rows': rows[0],
                'tagger_rows': rows[1],
                'catalogue_tags_cleared': cleared,
                'at': datetime.now(UTC).isoformat(),
            }
            log.write(json.dumps(record, ensure_ascii=False) + '\n')
            log.flush()
            if notify:
                notify([src, dst])
            done += 1
            media += rows[0]
            tagger += rows[1]
            tags += cleared
    return {
        'renamed': done,
        'skipped': skipped,
        'media_rows': media,
        'tagger_rows': tagger,
        'catalogue_tags_cleared': tags,
        'log': log_path,
    }


def rollback(
    log_path: str,
    eps_root: str,
    connection,
    rename: Callable[[str, str], None] = os.rename,
    notify: Callable[[list[str]], None] | None = None,
) -> dict:
    """Undoes a logged apply, newest first: folder name and stored paths.

    The cleared catalogue-number tags come back by themselves: with the word in front of the
    folder again, the next tagging round reads it from the path and writes it.
    """
    with open(log_path, encoding='utf-8') as handle:
        entries = [json.loads(line) for line in handle if line.strip()]
    restored, gone, blocked = 0, [], []
    for entry in reversed(entries):
        src = os.path.join(eps_root, entry['label'], entry['new'])
        dst = os.path.join(eps_root, entry['label'], entry['old'])
        if not os.path.isdir(src):
            gone.append(f"{entry['label']}/{entry['new']}")
            continue
        if os.path.exists(dst):
            blocked.append(f"{entry['label']}/{entry['old']}")
            continue
        _move(connection, src, dst, rename)
        if notify:
            notify([src, dst])
        restored += 1
    return {'restored': restored, 'missing': gone, 'old_name_taken': blocked}


def main(argv: list[str] | None = None) -> int:
    """Command-line entry: --dry-run, --backup-where, --apply or --rollback."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='Print the plan; change nothing.')
    mode.add_argument('--backup-where', choices=('media', 'tagger'), help='Print a mariadb-dump --where.')
    mode.add_argument('--apply', action='store_true', help='Rename the RENAME folders.')
    mode.add_argument('--rollback', metavar='LOG', help='Undo the renames recorded in LOG.')
    parser.add_argument('--log', help='Rename log to append to (required with --apply).')
    parser.add_argument('--json', help='Also write the full plan to this file.')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    from services.common.config_store import ConfigStore
    from services.common.Helpers.DatabaseConnector import DatabaseConnector
    from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
    from services.common.import_queue import ImportQueue

    settings = ConfigStore()
    eps_root = str(settings.eps_folder_path or '').strip()
    eps_root = os.path.normpath(eps_root) if eps_root else ''
    if not eps_root or not os.path.isdir(eps_root):
        print(f'EPs root not found: {eps_root!r}', file=sys.stderr)
        return 2
    if args.apply and not args.log:
        print('--apply needs --log', file=sys.stderr)
        return 2
    with DatabaseConnector().connection() as connection:
        if args.rollback:
            result = rollback(args.rollback, eps_root, connection, notify=lms_scan_trigger.notify)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        with connection.cursor() as cursor:
            rules = base.load_rules(cursor)
        folders = label_tree_folders(eps_root, ImportQueue.from_settings(settings))
        planned = plan(folders, rules)
        if args.backup_where:
            column = 'file_path' if args.backup_where == 'media' else 'filepath'
            print(backup_where(planned, eps_root, column))
            return 0
        if args.json:
            with open(args.json, 'w', encoding='utf-8') as handle:
                json.dump([asdict(entry) for entry in planned], handle, indent=1, ensure_ascii=False)
        for entry in planned:
            target = entry.new if entry.verdict == 'rename' else entry.reason
            print(f'{entry.verdict.upper():<9}\t{entry.old_path!r}\t{target}')
        print(json.dumps({'eps_root': eps_root, **summarize(planned, len(folders))}, indent=2, ensure_ascii=False))
        if args.apply:
            result = apply_plan(planned, eps_root, args.log, connection, notify=lms_scan_trigger.notify)
            print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
