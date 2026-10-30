"""A fresh database from the init has the shape production has.

tests/integration/schema/production.tsv is production's schema as
`python -m services.common.schema_reconcile --snapshot` prints it, read on production
(docs/designs/declarative-schema/technical.md). A fresh database built by the init is read
the same way and the two are compared line by line: tables, columns with type, default and
collation, indexes, foreign keys, checks and views.

A change to a declaration in services/common/schema_tables.py that production does not have
yet fails here until the snapshot is refreshed after the deploy that brings it, or the line
is in the lists below with its reason.
"""

from pathlib import Path

import pytest

from services.common import schema_reconcile

pytestmark = pytest.mark.integration

SNAPSHOT = Path(__file__).parent / 'schema' / 'production.tsv'

CLEANUP = 'tools/schema_cleanup_2026_11.py'

# Tables production has and the code no longer declares. Nothing reads or writes them; the
# cleanup script drops them with a backup.
DROPPED_TABLES = {
    'downloads_soundcloud_queue': f'never read since the queue moved into the archive; {CLEANUP}',
    'downloads_youtube_queue': f'never read since the queue moved into the archive; {CLEANUP}',
    'rules_genres_new': f'left behind by the genre-state rebuild; {CLEANUP}',
    'rules_genres_old': f'left behind by the genre-state rebuild; {CLEANUP}',
    'library_broken_songs': f'written on a failed tag and never read, 0 rows; {CLEANUP}',
    'library_broken_song_artist_lookup': f'BrokenSongArtistLookupHelper was never called; {CLEANUP}',
    'schema_migrations': 'the ledger of the migration files, kept on production as a record',
}

# Columns production has and the code no longer declares, for the same reason.
DROPPED_COLUMNS = {
    ('artist_external_ids', 'confidence'): CLEANUP,
    ('downloads_soundcloud_accounts', 'account_type'): CLEANUP,
    ('downloads_soundcloud_accounts', 'image_enrichment_hint'): CLEANUP,
    ('downloads_soundcloud_accounts', 'linked_artist_id'): CLEANUP,
    ('library_artist_images', 'status'): CLEANUP,
    ('library_artist_images', 'error_message'): CLEANUP,
}

# Other lines production has and a fresh database does not, each with its reason.
ONLY_ON_PRODUCTION = {
    'F\tscrobble_listens\ttrack_id\tlibrary_tracks\tid\tCASCADE\tRESTRICT': (
        f'a deleted track took its listens with it; the cleanup script makes it SET NULL ({CLEANUP})'
    ),
}

# Lines a fresh database has and production does not, each with its reason. The deploy's
# reconcile adds the columns and the index; the cleanup script adds the foreign keys.
ONLY_ON_FRESH = {
    'C\tlibrary_artists\tcreated_at\ttimestamp\tYES\tcurrent_timestamp()\t\t<none>': 'added by the reconcile',
    'C\tlibrary_labels\tcreated_at\ttimestamp\tYES\tcurrent_timestamp()\t\t<none>': 'added by the reconcile',
    'I\trules_genres\tcanonical_id\t0\tcanonical_id\tBTREE': 'added by the reconcile',
    'F\trules_genres\tcanonical_id\trules_genres\tid\tSET NULL\tRESTRICT': CLEANUP,
    'F\tscrobble_listens\ttrack_id\tlibrary_tracks\tid\tSET NULL\tRESTRICT': CLEANUP,
}


def _production_lines() -> set[str]:
    return {line for line in SNAPSHOT.read_text(encoding='utf-8').splitlines() if line}


def _dropped(line: str) -> bool:
    """True for a line of a table or column the cleanup script drops."""
    kind, table, *rest = line.split('\t')
    return table in DROPPED_TABLES or (kind == 'C' and (table, rest[0]) in DROPPED_COLUMNS)


def test_a_fresh_database_equals_the_production_snapshot(fresh_schema):
    """Every difference is either listed above with its reason, or a fault."""
    fresh = set(schema_reconcile.snapshot_lines(fresh_schema))
    production = _production_lines()
    only_production = sorted(
        line for line in production - fresh if line not in ONLY_ON_PRODUCTION and not _dropped(line)
    )
    only_fresh = sorted(fresh - production - set(ONLY_ON_FRESH))
    assert not only_production and not only_fresh, (
        'schema differs from tests/integration/schema/production.tsv\n'
        + ''.join(f'  only on production: {line}\n' for line in only_production)
        + ''.join(f'  only in a fresh database: {line}\n' for line in only_fresh)
    )


def test_every_listed_difference_still_exists(fresh_schema):
    """A listed item that no longer differs is stale: remove it, so the lists stay a list of work."""
    fresh = set(schema_reconcile.snapshot_lines(fresh_schema))
    production = _production_lines()
    differing = production - fresh
    stale = sorted(set(ONLY_ON_PRODUCTION) - differing) + sorted(set(ONLY_ON_FRESH) - (fresh - production))
    stale += sorted(t for t in DROPPED_TABLES if not any(line.split('\t')[1] == t for line in differing))
    stale += sorted(
        f'{t}.{c}' for t, c in DROPPED_COLUMNS if not any(line.startswith(f'C\t{t}\t{c}\t') for line in differing)
    )
    assert stale == []
