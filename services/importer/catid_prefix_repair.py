"""Repairs import folders the Renamer gave an empty catalogue-number prefix.

When `Renamer.find_cat_id` finds no parenthesised group with a digit in a release folder's name it
still prefixes the separator, so `Artist_-_Title-WEB-2025` became ` - Artist_-_Title-WEB-2025`. The
Mover reads the catalogue number from before the first space, finds '', and records a label proposal
instead of moving the release. 2.613 such folders had a proposal row on production on 2026-09-25.

Stripping the prefix would not help: the Renamer renames any folder without "- " in its name again
on the next cycle. The only repair is a real catalogue number in front, and only when that number
actually routes the release -- i.e. when the prefix `Mover.get_cat_id` reads from it is a key of
`rules_catid_label`. A number the rules do not know would just produce the same proposal under a
new name. So the planner tries, in order:

  1. the catalogue number the proposal row carries (read from the release's own tags by the
     label resolver) -- many of those are UPCs or distributor ids, which the rule check drops;
  2. a token in the folder name whose prefix is a known rule key: a parenthesised group
     (`(RRBM)`) or a word holding letters and digits (`DWX123`).

Anything else is listed as undecidable with the reason, never guessed. A folder whose rule label
contradicts the label a person already decided on the proposal is undecidable too.

Apply renames inside the import queue only, moves the proposal row along with the folder, and logs
every rename as one JSON line before the next one starts, so `--rollback <log>` can put it back.
After a rename the next import cycle's Mover places the release under its label -- that is the
point -- and a release it has moved can no longer be rolled back from here; rollback reports it.

    python -m services.importer.catid_prefix_repair --dry-run [--json plan.json]
    python -m services.importer.catid_prefix_repair --apply --log /data/catid-prefix-renames.jsonl
    python -m services.importer.catid_prefix_repair --rollback /data/catid-prefix-renames.jsonl

Bug report 087, docs/designs/todo-label-backlog/.
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

from services.importer.mover import get_cat_id
from services.importer.settle import is_staging

#: What the Renamer puts in front of a folder it found no catalogue number for.
CROOKED_PREFIX = ' - '

#: Values the resolver reads from tags that are never a catalogue number.
JUNK_CATIDS = {'', 'none', 'null', 'n/a', 'na', '-', 'unknown'}

# Tokens of a scene folder name: separated by whitespace, underscores, dots and dashes.
_TOKEN_SPLIT = re.compile(r'[\s_.\-]+')
_PAREN_GROUP = re.compile(r'\(([^()]*)\)')
_UNSAFE = re.compile(r'[/\\\x00]')


@dataclass(frozen=True)
class Proposal:
    """What `rules_label_proposals` knows about one queue folder."""

    catid: str | None
    proposed_label: str | None
    decided_label: str | None


@dataclass(frozen=True)
class PlannedRename:
    """One crooked folder and what the planner would do with it."""

    old: str
    new: str | None
    catid: str | None
    source: str | None
    label: str | None
    reason: str


def is_crooked(name: str) -> bool:
    """Whether a queue folder carries the Renamer's empty catalogue-number prefix."""
    return name.startswith(CROOKED_PREFIX)


def rule_prefix(catid: str) -> str:
    """The prefix the Mover would look up for a folder named `<catid> - ...`."""
    return get_cat_id(f'{catid} x') or ''


def _clean_catid(value: str | None) -> str:
    return re.sub(r'\s+', '', value or '').strip()


def _usable(catid: str, rules: dict[str, str]) -> str | None:
    """The rule label a catalogue number routes to, or None when it routes nowhere."""
    if catid.lower() in JUNK_CATIDS or _UNSAFE.search(catid):
        return None
    prefix = rule_prefix(catid)
    if not prefix:
        return None
    return rules.get(prefix.lower())


def name_candidates(rest: str) -> list[str]:
    """Catalogue-number candidates in a folder name, in order of appearance, without repeats."""
    found: list[str] = []
    for group in _PAREN_GROUP.findall(rest):
        cleaned = _clean_catid(group)
        if cleaned:
            found.append(cleaned)
    for token in _TOKEN_SPLIT.split(_PAREN_GROUP.sub(' ', rest)):
        if re.search(r'[A-Za-z]', token) and re.search(r'\d', token):
            found.append(token)
    return list(dict.fromkeys(found))


def plan_one(name: str, proposal: Proposal | None, rules: dict[str, str]) -> PlannedRename:
    """What to do with one crooked folder. `rules` maps a lowercased rule prefix to its label."""
    rest = name[len(CROOKED_PREFIX) :]
    catid: str | None = None
    source: str | None = None
    label: str | None = None
    from_proposal = _clean_catid(proposal.catid if proposal else None)
    if from_proposal:
        label = _usable(from_proposal, rules)
        if label:
            catid, source = from_proposal, 'proposal'
    if catid is None:
        routed = {candidate: _usable(candidate, rules) for candidate in name_candidates(rest)}
        routed = {candidate: rule for candidate, rule in routed.items() if rule}
        labels = {rule.lower() for rule in routed.values()}
        if len(labels) > 1:
            listed = ', '.join(f'{c}->{r}' for c, r in routed.items())
            return PlannedRename(name, None, None, None, None, f'ambiguous: {listed}')
        if routed:
            catid, label = next(iter(routed.items()))
            source = 'name'
    if catid is None or label is None:
        return PlannedRename(name, None, None, None, None, 'no catalogue number a rule knows')
    decided = (proposal.decided_label or '').strip() if proposal else ''
    if decided and decided.lower() != label.lower():
        return PlannedRename(name, None, catid, source, label, f'rule says {label}, decided label is {decided}')
    return PlannedRename(name, f'{catid}{CROOKED_PREFIX}{rest}', catid, source, label, 'ok')


def plan(folders: Iterable[str], proposals: dict[str, Proposal], rules: dict[str, str]) -> list[PlannedRename]:
    """Plans every crooked folder in `folders`, refusing any rename onto a name already taken."""
    existing = set(folders)
    taken: set[str] = set()
    planned: list[PlannedRename] = []
    for name in sorted(existing):
        if not is_crooked(name) or is_staging(name):
            continue
        entry = plan_one(name, proposals.get(name), rules)
        if entry.new is not None and (entry.new in existing or entry.new in taken):
            entry = PlannedRename(name, None, entry.catid, entry.source, entry.label, f'target exists: {entry.new}')
        if entry.new is not None:
            taken.add(entry.new)
        planned.append(entry)
    return planned


def summarize(planned: list[PlannedRename]) -> dict:
    """Counts for a plan: renameable, undecidable by reason, per label."""
    renames = [entry for entry in planned if entry.new]
    reasons: dict[str, int] = {}
    for entry in planned:
        if not entry.new:
            key = entry.reason.split(':')[0]
            reasons[key] = reasons.get(key, 0) + 1
    labels: dict[str, int] = {}
    for entry in renames:
        labels[str(entry.label)] = labels.get(str(entry.label), 0) + 1
    return {
        'crooked': len(planned),
        'renameable': len(renames),
        'by_source': {src: sum(1 for e in renames if e.source == src) for src in ('proposal', 'name')},
        'undecidable': reasons,
        'by_label': dict(sorted(labels.items(), key=lambda item: -item[1])),
    }


# ---------------------------------------------------------------------------- side effects


def load_proposals(cursor) -> dict[str, Proposal]:
    """Every proposal row keyed on folder name. The table is a few thousand rows."""
    cursor.execute('SELECT folder, catid, proposed_label, decided_label FROM rules_label_proposals')
    return {str(row[0]): Proposal(row[1], row[2], row[3]) for row in cursor.fetchall()}


def load_rules(cursor) -> dict[str, str]:
    """`rules_catid_label` keyed on the lowercased prefix."""
    cursor.execute('SELECT catid, label FROM rules_catid_label')
    return {str(row[0]).lower(): str(row[1]) for row in cursor.fetchall()}


def _move_proposal(cursor, old: str, new: str) -> None:
    """Carry the proposal row along with the folder, unless the new name already has one."""
    cursor.execute(
        'UPDATE rules_label_proposals SET folder = %s WHERE folder = %s '
        'AND NOT EXISTS (SELECT 1 FROM (SELECT folder FROM rules_label_proposals WHERE folder = %s) taken)',
        (new, old, new),
    )


def apply_plan(
    planned: list[PlannedRename],
    queue_path: str,
    log_path: str,
    connection,
    rename: Callable[[str, str], None] = os.rename,
    notify: Callable[[list[str]], None] | None = None,
) -> dict:
    """Renames every planned folder, logging each one before the next starts."""
    done = skipped = 0
    with open(log_path, 'a', encoding='utf-8') as log:
        for entry in planned:
            if not entry.new:
                continue
            src = os.path.join(queue_path, entry.old)
            dst = os.path.join(queue_path, entry.new)
            if not os.path.isdir(src) or os.path.exists(dst):
                skipped += 1
                continue
            rename(src, dst)
            log.write(json.dumps({'old': entry.old, 'new': entry.new, 'at': datetime.now(UTC).isoformat()}) + '\n')
            log.flush()
            with connection.cursor() as cursor:
                _move_proposal(cursor, entry.old, entry.new)
            connection.commit()
            if notify:
                notify([src, dst])
            done += 1
    return {'renamed': done, 'skipped': skipped, 'log': log_path}


def rollback(
    log_path: str,
    queue_path: str,
    connection,
    rename: Callable[[str, str], None] = os.rename,
    notify: Callable[[list[str]], None] | None = None,
) -> dict:
    """Undoes a logged apply, newest first. A folder the Mover has since placed is reported, not chased."""
    with open(log_path, encoding='utf-8') as handle:
        entries = [json.loads(line) for line in handle if line.strip()]
    restored, gone, blocked = 0, [], []
    for entry in reversed(entries):
        src = os.path.join(queue_path, entry['new'])
        dst = os.path.join(queue_path, entry['old'])
        if not os.path.isdir(src):
            gone.append(entry['new'])
            continue
        if os.path.exists(dst):
            blocked.append(entry['old'])
            continue
        rename(src, dst)
        with connection.cursor() as cursor:
            _move_proposal(cursor, entry['new'], entry['old'])
        connection.commit()
        if notify:
            notify([src, dst])
        restored += 1
    return {'restored': restored, 'no_longer_in_queue': gone, 'old_name_taken': blocked}


def _queue_folders(queue_path: str) -> list[str]:
    return [name for name in os.listdir(queue_path) if os.path.isdir(os.path.join(queue_path, name))]


def main(argv: list[str] | None = None) -> int:
    """Command-line entry: --dry-run, --apply or --rollback."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='Print the plan; change nothing.')
    mode.add_argument('--apply', action='store_true', help='Rename the decidable folders.')
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
    with DatabaseConnector().connection() as connection:
        if args.rollback:
            print(json.dumps(rollback(args.rollback, queue_path, connection, notify=lms_scan_trigger.notify), indent=2))
            return 0
        with connection.cursor() as cursor:
            proposals = load_proposals(cursor)
            rules = load_rules(cursor)
        planned = plan(_queue_folders(queue_path), proposals, rules)
        if args.json:
            with open(args.json, 'w', encoding='utf-8') as handle:
                json.dump([asdict(entry) for entry in planned], handle, indent=1, ensure_ascii=False)
        for entry in planned:
            print(f'{"RENAME" if entry.new else "SKIP  "}\t{entry.old!r}\t{entry.new or entry.reason}')
        print(json.dumps({'queue': queue_path, **summarize(planned)}, indent=2, ensure_ascii=False))
        if args.apply:
            if not args.log:
                print('--apply needs --log', file=sys.stderr)
                return 2
            print(json.dumps(apply_plan(planned, queue_path, args.log, connection, notify=lms_scan_trigger.notify)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
