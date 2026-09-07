"""What a file said before the tagger touched it, and what the system was at that moment.

The tagger rewrites tags in place and keeps no copy of what was there. `ORIGINAL_TITLE`
and `ORIGINAL_ARTIST` are the two fields somebody noticed losing and then hand-rolled a
rescue for, each in its own rule, each conditional on the specific path that loses it.
Nothing records the rest, so "what did this file arrive with" has no answer -- and neither
does "which rule decided that", because the rules live in MariaDB and change.

This writes one row per file, the first time the tagger opens it, holding the whole tag
set as read plus the version of the code and a fingerprint of the rules in force. That is
what makes a decision reviewable afterwards: the arrival state and the ruleset that acted
on it. It is deliberately not a copy of the file -- the audio stream is not what the
tagger changes, and 5,3 TB of duplicated audio would answer a question nobody asked.

Written once and never updated. A later pass sees a file the tagger has already rewritten,
so its idea of "arrival" is worth less than the first one's; `INSERT IGNORE` is what keeps
the earliest answer.

Best effort throughout. An unreachable database must not stop a tagging round -- losing
the record is a smaller loss than losing the round.
"""

import hashlib
import json
import logging
import os
from pathlib import Path

from services.common.Helpers.DatabaseConnector import DatabaseConnector

#: Tables whose contents decide what the tagger writes. The fingerprint below is built
#: from these, so a row can say "these were the rules" without copying them.
RULE_TABLES = (
    'rules_genres',
    'rules_genre_expansions',
    'rules_artist_genres',
    'rules_label_genres',
    'rules_subgenre_hierarchy',
    'rules_ignored_artists',
    'rules_catid_label',
)

_rules_fingerprint: str | None = None


def code_version() -> str:
    """The repository's VERSION, or 'unknown'.

    Read off disk rather than injected at build time because every image in this repo
    already ships the file, and a version that only exists in CI is one more thing that
    can be missing exactly when the record matters.
    """
    for candidate in (Path(__file__).resolve().parents[2] / 'VERSION', Path('/app/VERSION')):
        try:
            return candidate.read_text(encoding='utf-8').strip() or 'unknown'
        except OSError:
            continue
    return 'unknown'


def rules_fingerprint(refresh: bool = False) -> str:
    """A short digest of the rule tables' current contents.

    Cached for the life of the process: this is one query per tagging round, not one per
    file. A round that starts after a curation decision gets the new value because the
    round is what refreshes the helpers anyway; a decision made mid-round belongs to the
    next one.

    Row counts and the newest decision timestamp rather than the rows themselves -- enough
    to tell two rulesets apart and to look up what changed, without copying a curated
    table into every track's row.
    """
    global _rules_fingerprint  # noqa: PLW0603 - one cache for the process, by design
    if _rules_fingerprint is not None and not refresh:
        return _rules_fingerprint
    parts: list[str] = []
    try:
        with DatabaseConnector().connection() as conn, conn.cursor() as cursor:
            for table in RULE_TABLES:
                try:
                    cursor.execute(f'SELECT COUNT(*) FROM {table}')  # noqa: S608 - fixed list above
                    row = cursor.fetchone()
                    parts.append(f'{table}={row[0] if row else 0}')
                except Exception as e:
                    # A table this deployment does not have yet is a fact about the
                    # ruleset too, and a better one than refusing the whole fingerprint.
                    logging.debug('Rule table %s unreadable for the fingerprint: %s', table, e)
                    parts.append(f'{table}=?')
    except Exception as e:
        logging.warning('Could not fingerprint the rules: %s', e)
        return 'unknown'
    _rules_fingerprint = hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:16]
    return _rules_fingerprint


def arrival_tags(song) -> dict[str, list[str]]:
    """Every tag on the file, as read, before any rule has run."""
    tags: dict[str, list[str]] = {}
    try:
        for name, tag in (song.tag_collection.get() or {}).items():
            try:
                tags[str(name)] = [str(value) for value in tag.to_array()]
            except AttributeError:
                tags[str(name)] = [str(tag)]
    except Exception as e:
        logging.debug('Could not read the arrival tags of %s: %s', getattr(song, '_path', '?'), e)
    return tags


def record(song, source: str) -> bool:
    """Write the arrival record for `song`. Returns whether a row was written.

    False covers both "already recorded" and "could not record", which the caller treats
    the same way: neither is a reason to stop tagging the file.
    """
    path = getattr(song, '_path', None)
    if not path or not getattr(song, 'tag_collection', None):
        return False
    tags = arrival_tags(song)
    if not tags:
        # A file with no tags at all is the one case where the record says nothing the
        # path does not already say.
        return False
    try:
        size = os.path.getsize(path)
    except OSError:
        size = None
    try:
        with DatabaseConnector().connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                'INSERT IGNORE INTO library_ingestion_records '
                '(file_path, file_path_hash, file_size, source, tags_json, code_version, rules_fingerprint) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (
                    path,
                    hashlib.sha256(path.encode('utf-8')).hexdigest(),
                    size,
                    source,
                    json.dumps(tags, ensure_ascii=False),
                    code_version(),
                    rules_fingerprint(),
                ),
            )
            written = cursor.rowcount > 0
            conn.commit()
        return written
    except Exception as e:
        logging.warning('Could not record the arrival of %s: %s', path, e)
        return False
