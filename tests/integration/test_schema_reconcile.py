"""services/common/schema_reconcile.py against a real MariaDB.

The deploy runs the reconcile before the new containers start
(docs/designs/declarative-schema/technical.md). These tests build a fresh database, take
something away or add something, and check that the reconcile puts back only what is missing
and reports the rest.
"""

import pymysql
import pytest

from services.common import schema_reconcile
from tests.integration import schema_sources
from tests.integration.conftest import _connect, _unavailable

pytestmark = pytest.mark.integration

LIVE = 'muma_test_reconcile_live'
PROBE = 'muma_test_reconcile_probe'


@pytest.fixture(name='live')
def live_fixture(database):
    """A fresh database built the way a new stack builds it, dropped afterwards."""
    try:
        with database.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS `{LIVE}`')
            cursor.execute(f'CREATE DATABASE `{LIVE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
    except pymysql.err.MySQLError as exc:
        _unavailable(f'cannot create the scratch database {LIVE} ({exc}); see scripts/test/db-integration.sh')
    connection = _connect(database=LIVE)
    schema_sources.build_fresh(connection, LIVE)
    yield connection
    connection.close()
    with database.cursor() as cursor:
        cursor.execute(f'DROP DATABASE IF EXISTS `{LIVE}`')
        cursor.execute(f'DROP DATABASE IF EXISTS `{PROBE}`')


def _reconcile(connection, *, dry_run=False):
    return schema_reconcile.reconcile(connection, LIVE, PROBE, dry_run=dry_run, lock_wait_seconds=5)


def _run(connection, *statements):
    with connection.cursor() as cursor:
        cursor.execute(f'USE `{LIVE}`')
        for statement in statements:
            cursor.execute(statement)


def _snapshot(connection):
    with connection.cursor() as cursor:
        return schema_reconcile.snapshot_lines(schema_reconcile.read_schema(cursor, LIVE))


def test_a_fresh_database_is_in_sync(live):
    result = _reconcile(live)
    assert (result.statements, result.reports) == ([], [])


def test_the_probe_is_dropped_again(live):
    _reconcile(live, dry_run=True)
    with live.cursor() as cursor:
        cursor.execute('SHOW DATABASES LIKE %s', (PROBE,))
        assert not cursor.fetchall()


def test_a_missing_column_index_table_and_view_come_back_and_a_second_run_is_a_no_op(live):
    before = _snapshot(live)
    _run(
        live,
        'ALTER TABLE library_tracks DROP COLUMN performance_date',
        'ALTER TABLE library_tracks DROP INDEX idx_tracks_form',
        'DROP VIEW rules_label_genre',
        'DROP TABLE library_track_effective_bpm',
    )

    first = _reconcile(live)
    assert len(first.statements) == 4, first.statements
    assert first.reports == []
    assert _snapshot(live) == before
    assert _reconcile(live).statements == []


def test_a_dry_run_changes_nothing(live):
    _run(live, 'ALTER TABLE library_tracks DROP COLUMN performance_date')
    before = _snapshot(live)
    assert _reconcile(live, dry_run=True).statements
    assert _snapshot(live) == before


def test_extra_and_changed_objects_are_reported_and_kept(live):
    _run(
        live,
        'ALTER TABLE library_labels ADD COLUMN legacy_note TEXT',
        'ALTER TABLE library_labels MODIFY mbid VARCHAR(100)',
        'CREATE TABLE legacy_things (id INT PRIMARY KEY)',
    )
    before = _snapshot(live)

    result = _reconcile(live)

    assert result.statements == []
    kinds = sorted(report.split(':')[0] for report in result.reports)
    assert kinds == ['changed column', 'extra column', 'extra table']
    assert _snapshot(live) == before


def test_a_unique_index_the_data_violates_stops_the_reconcile(live):
    _run(
        live,
        'ALTER TABLE rules_genres DROP INDEX uq_rules_genres_normalized_name',
        "INSERT INTO rules_genres (name, normalized_name) VALUES ('Hardcore', 'twice'), ('HARDCORE', 'twice')",
    )
    with pytest.raises(pymysql.err.IntegrityError):
        _reconcile(live)
