"""Gives import folders back the name the Renamer took from them (bug report 145).

Before bug report 145 the Renamer put a prefix in front of every release folder that had no
"- " in its name: the last parenthesised group with a digit, or nothing at all. That left two
kinds of folder in the import queue that no catalogue-number rule can ever route:

* ` - Guizcore_-_Coffee_Time-WEB-FLAC-2026` -- an empty prefix (2.663 on production on
  2026-10-02, plus one written as `- ...` without the leading space);
* `Official_Hardbass_2026_Anthem - Minus_Militia_And_Nolz_-_Recover_The_Archive_(...)` -- a
  word group taken for a catalogue number (96).

Now that the Renamer leaves a name without a catalogue number alone, the prefix can simply go.
For every such folder the planner computes the name the Renamer would give it today:

  1. for an empty prefix, a catalogue number a `rules_catid_label` rule already routes, found the
     way `catid_prefix_repair` finds it (the proposal row's number, or a token in the name);
  2. otherwise the catalogue number the name itself carries under the new rule
     (`DKR_-_..._(ESU054)-WEB-2026 (1)` was prefixed `1 - `, and becomes `ESU054 - ...`);
  3. otherwise the bare original name.

A word prefix is only removed when it is exactly what the old Renamer would have produced for the
rest of the name and the new rule refuses it, so a prefix a person typed (`HZH - VA_-_...`) stays.
A rename onto a name already taken is refused and listed. Renames, the proposal-row move, the log
and the rollback are `catid_prefix_repair`'s, so a log from either tool rolls back the same way.

    python -m services.importer.prefix_strip_repair --dry-run [--json plan.json]
    python -m services.importer.prefix_strip_repair --apply --log /tmp/prefix-strip.jsonl
    python -m services.importer.prefix_strip_repair --rollback /tmp/prefix-strip.jsonl

Run it only where the importer already has the bug-report-145 Renamer; an older one would put
the prefixes straight back. repair-word-prefixed-import-folders.sh wraps it.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, replace

from services.common.catalogue_number import from_folder_name, old_rule_prefix, rejection
from services.importer import catid_prefix_repair as base
from services.importer.catid_prefix_repair import PlannedRename, Proposal
from services.importer.settle import is_staging

#: The two spellings of the empty prefix found on production.
EMPTY_PREFIXES = (' - ', '- ')

_PREFIXED = re.compile(r'^(\S+) - (.*)$', re.S)


def crooked_rest(name: str) -> tuple[str, str] | None:
    """`(kind, original name)` for a folder the old Renamer misnamed, else None.

    `kind` is `empty` for an empty prefix and `word` for a refused word prefix.
    """
    for prefix in EMPTY_PREFIXES:
        if name.startswith(prefix):
            rest = name[len(prefix) :]
            return ('empty', rest) if rest.strip() else None
    match = _PREFIXED.match(name)
    if not match:
        return None
    prefix, rest = match.groups()
    if old_rule_prefix(rest) == prefix and rejection(prefix) is not None:
        return ('word', rest)
    return None


def plan_one(name: str, proposal: Proposal | None, rules: dict[str, str]) -> PlannedRename | None:
    """What to do with one queue folder, or None when it is not one of the misnamed kinds."""
    found = crooked_rest(name)
    if found is None:
        return None
    kind, rest = found
    if kind == 'empty':
        routed = base.plan_one(' - ' + rest, proposal, rules)
        if routed.new is not None:
            return replace(routed, old=name)
    catalogue_number = from_folder_name(rest)
    if catalogue_number:
        return PlannedRename(
            name, f'{catalogue_number} - {rest}', catalogue_number, 'name', None, f'{kind} prefix; name carries one'
        )
    return PlannedRename(name, rest, None, 'strip', None, f'{kind} prefix removed')


def plan(folders: Iterable[str], proposals: dict[str, Proposal], rules: dict[str, str]) -> list[PlannedRename]:
    """Plans every misnamed folder in `folders`, refusing a rename onto a name already taken."""
    existing = set(folders)
    taken: set[str] = set()
    planned: list[PlannedRename] = []
    for name in sorted(existing):
        if is_staging(name):
            continue
        entry = plan_one(name, proposals.get(name), rules)
        if entry is None:
            continue
        if entry.new is not None and (entry.new in existing or entry.new in taken):
            entry = PlannedRename(name, None, entry.catid, entry.source, entry.label, f'target exists: {entry.new}')
        if entry.new is not None:
            taken.add(entry.new)
        planned.append(entry)
    return planned


def summarize(planned: list[PlannedRename]) -> dict:
    """Counts for a plan: misnamed folders, renames by source, refusals by reason."""
    renames = [entry for entry in planned if entry.new]
    refused: dict[str, int] = {}
    for entry in planned:
        if not entry.new:
            key = entry.reason.split(':')[0]
            refused[key] = refused.get(key, 0) + 1
    by_source: dict[str, int] = {}
    for entry in renames:
        by_source[str(entry.source)] = by_source.get(str(entry.source), 0) + 1
    return {
        'misnamed': len(planned),
        'empty_prefix': sum(1 for entry in planned if entry.old.startswith(EMPTY_PREFIXES)),
        'word_prefix': sum(1 for entry in planned if not entry.old.startswith(EMPTY_PREFIXES)),
        'renameable': len(renames),
        'by_source': by_source,
        'refused': refused,
    }


def queue_folders(queue_path: str) -> list[str]:
    """The directories directly inside the import queue."""
    return [name for name in os.listdir(queue_path) if os.path.isdir(os.path.join(queue_path, name))]


def main(argv: list[str] | None = None) -> int:
    """Command-line entry: --dry-run, --apply or --rollback."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='Print the plan; change nothing.')
    mode.add_argument('--apply', action='store_true', help='Rename the misnamed folders.')
    mode.add_argument('--rollback', metavar='LOG', help='Undo the renames recorded in LOG.')
    parser.add_argument('--log', help='Rename log to append to (required with --apply).')
    parser.add_argument('--json', help='Also write the full plan to this file.')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    from services.common.Helpers.DatabaseConnector import DatabaseConnector
    from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
    from services.common.import_queue import ImportQueue

    queue_path = ImportQueue.from_settings().path
    if not queue_path or not os.path.isdir(queue_path):
        print(f'import queue not found: {queue_path!r}', file=sys.stderr)
        return 2
    if args.apply and not args.log:
        print('--apply needs --log', file=sys.stderr)
        return 2
    with DatabaseConnector().connection() as connection:
        if args.rollback:
            result = base.rollback(args.rollback, queue_path, connection, notify=lms_scan_trigger.notify)
            print(json.dumps(result, indent=2))
            return 0
        with connection.cursor() as cursor:
            proposals = base.load_proposals(cursor)
            rules = base.load_rules(cursor)
        planned = plan(queue_folders(queue_path), proposals, rules)
        if args.json:
            with open(args.json, 'w', encoding='utf-8') as handle:
                json.dump([asdict(entry) for entry in planned], handle, indent=1, ensure_ascii=False)
        for entry in planned:
            print(f'{"RENAME" if entry.new else "SKIP  "}\t{entry.old!r}\t{entry.new or entry.reason}')
        print(json.dumps({'queue': queue_path, **summarize(planned)}, indent=2, ensure_ascii=False))
        if args.apply:
            result = base.apply_plan(planned, queue_path, args.log, connection, notify=lms_scan_trigger.notify)
            print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
