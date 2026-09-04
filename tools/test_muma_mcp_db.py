"""Read-only database access, tools/muma_mcp/db.py. No test opens a connection."""

from __future__ import annotations

import datetime
import decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.muma_mcp import db
from tools.muma_mcp.config import Config
from tools.muma_mcp.guard import QueryRejected

CONFIG = Config(
    prod_url='http://192.0.2.27:8000',
    api_key='key',
    db_host='192.0.2.27',
    db_port=3306,
    db_user='muma-readonly',
    db_pass='pw',
    db_name='music-management',
)


def fake_connection(rows, description=(('id',), ('title',))):
    """A connection whose cursor replays ``rows`` and records the SQL it was given."""
    cursor = MagicMock()
    cursor.description = description
    cursor.fetchmany.side_effect = lambda size: rows[:size]
    cursor.fetchall.return_value = rows
    cursor.__enter__ = lambda self: cursor
    cursor.__exit__ = lambda self, *args: False

    connection = MagicMock()
    connection.cursor.return_value = cursor
    return connection, cursor


def test_run_query_returns_columns_and_rows():
    connection, _ = fake_connection([(1, 'a'), (2, 'b')])
    with patch('tools.muma_mcp.db.connect', return_value=connection):
        result = db.run_query(CONFIG, 'SELECT id, title FROM library_tracks')

    assert result['columns'] == ['id', 'title']
    assert result['rows'] == [{'id': 1, 'title': 'a'}, {'id': 2, 'title': 'b'}]
    assert result['row_count'] == 2
    assert result['truncated'] is False


def test_run_query_opens_a_read_only_transaction():
    connection, cursor = fake_connection([])
    with patch('tools.muma_mcp.db.connect', return_value=connection):
        db.run_query(CONFIG, 'SELECT 1')

    executed = [call.args[0] for call in cursor.execute.call_args_list]
    assert 'START TRANSACTION READ ONLY' in executed


def test_run_query_rejects_a_write_before_connecting():
    """The guard runs first: a DELETE never reaches the database at all."""
    with patch('tools.muma_mcp.db.connect') as connect:
        with pytest.raises(QueryRejected):
            db.run_query(CONFIG, 'DELETE FROM library_tracks')

    connect.assert_not_called()


def test_the_query_is_not_rewritten_to_carry_a_limit():
    """Editing the SQL would silently answer a different question."""
    connection, cursor = fake_connection([])
    with patch('tools.muma_mcp.db.connect', return_value=connection):
        db.run_query(CONFIG, 'SELECT id FROM library_tracks', limit=5)

    executed = [call.args[0] for call in cursor.execute.call_args_list]
    assert 'SELECT id FROM library_tracks' in executed
    assert not any('LIMIT 5' in statement for statement in executed)


def test_truncation_is_reported_rather_than_hidden():
    connection, cursor = fake_connection([(n, 'x') for n in range(10)])
    with patch('tools.muma_mcp.db.connect', return_value=connection):
        result = db.run_query(CONFIG, 'SELECT id, title FROM library_tracks', limit=3)

    cursor.fetchmany.assert_called_once_with(4)
    assert result['row_count'] == 3
    assert result['truncated'] is True
    assert 'limit=3' in result['truncated_reason']


def test_a_result_that_exactly_fits_is_not_marked_truncated():
    connection, _ = fake_connection([(1, 'a'), (2, 'b'), (3, 'c')])
    with patch('tools.muma_mcp.db.connect', return_value=connection):
        result = db.run_query(CONFIG, 'SELECT id, title FROM library_tracks', limit=3)

    assert result['truncated'] is False
    assert result['truncated_reason'] is None


def test_an_oversized_result_is_cut_and_says_why():
    wide = 'x' * 5000
    connection, _ = fake_connection([(n, wide) for n in range(100)])
    with patch('tools.muma_mcp.db.connect', return_value=connection):
        result = db.run_query(CONFIG, 'SELECT id, title FROM library_tracks', limit=100)

    assert result['truncated'] is True
    assert 'bytes' in result['truncated_reason']
    assert result['row_count'] < 100


@pytest.mark.parametrize(('requested', 'expected_fetch'), [(0, 2), (-1, 2), (5000, 1001)])
def test_limit_is_clamped(requested, expected_fetch):
    connection, cursor = fake_connection([])
    with patch('tools.muma_mcp.db.connect', return_value=connection):
        db.run_query(CONFIG, 'SELECT 1', limit=requested)

    cursor.fetchmany.assert_called_once_with(expected_fetch)


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (datetime.datetime(2026, 9, 4, 12, 30), '2026-09-04T12:30:00'),
        (datetime.date(2026, 9, 4), '2026-09-04'),
        (decimal.Decimal('1.50'), '1.50'),
        (b'hello', 'hello'),
        (b'\xff\xfe', '<2 bytes binair>'),
        (None, None),
        (7, 7),
    ],
)
def test_row_values_are_made_json_safe(value, expected):
    assert db._jsonable(value) == expected


def test_describe_binds_the_table_name_instead_of_interpolating_it():
    """DESCRIBE takes no placeholder, so information_schema is asked instead.

    The name travels as a bound parameter -- data, never syntax -- which is why
    `describe` needs no validation of it and cannot forget any.
    """
    connection, cursor = fake_connection([('id', 'int(11)', 'NO', 'PRI', None, '')])
    with patch('tools.muma_mcp.db.connect', return_value=connection):
        db.describe(CONFIG, 'library_tracks')

    statement, params = cursor.execute.call_args.args
    assert 'information_schema' in statement.lower()
    assert 'library_tracks' not in statement
    assert params == ('music-management', 'library_tracks')


def test_describe_reports_a_table_that_does_not_exist():
    """An unknown name matches nothing rather than producing a syntax error."""
    connection, _ = fake_connection([])
    with (
        patch('tools.muma_mcp.db.connect', return_value=connection),
        pytest.raises(QueryRejected, match='bestaat niet'),
    ):
        db.describe(CONFIG, 'nope')


def test_describe_treats_injected_sql_as_a_missing_table():
    connection, _ = fake_connection([])
    with (
        patch('tools.muma_mcp.db.connect', return_value=connection),
        pytest.raises(QueryRejected, match='bestaat niet'),
    ):
        db.describe(CONFIG, 'library_tracks`; DROP TABLE x; --')


def test_list_tables_is_sorted():
    connection, _ = fake_connection([('zebra',), ('alpha',)])
    with patch('tools.muma_mcp.db.connect', return_value=connection):
        assert db.list_tables(CONFIG) == ['alpha', 'zebra']


class FakeDatabaseError(Exception):
    """Stands in for pymysql.MySQLError.

    services/tests/mock_base.py replaces the whole `pymysql` module with a
    MagicMock for the full-tree run, which leaves `pymysql.MySQLError` a mock
    rather than a class -- and `except <mock>` raises TypeError. Running
    `pytest tools/` on its own does not load that stub, so this only shows up in
    CI. Patching the module reference makes the test say what it means either
    way: a database error from the probe means the write was refused.
    """


def test_check_write_is_refused_passes_when_the_database_refuses():
    connection, cursor = fake_connection([])
    cursor.execute.side_effect = FakeDatabaseError('CREATE command denied')
    with (
        patch('tools.muma_mcp.db.pymysql', SimpleNamespace(MySQLError=FakeDatabaseError)),
        patch('tools.muma_mcp.db.connect', return_value=connection),
    ):
        assert db.check_write_is_refused(CONFIG) == 0


def test_check_write_is_refused_raises_when_the_write_succeeds():
    """An account that can create a table is not read-only and must not be used."""
    connection, _ = fake_connection([])
    with (
        patch('tools.muma_mcp.db.connect', return_value=connection),
        pytest.raises(db.WriteProbeSucceeded),
    ):
        db.check_write_is_refused(CONFIG)


def test_the_write_probe_runs_outside_the_read_only_transaction():
    """Inside one, every write fails regardless of privilege -- proving nothing."""
    connection, cursor = fake_connection([])
    with patch('tools.muma_mcp.db.connect', return_value=connection):
        with pytest.raises(db.WriteProbeSucceeded):
            db.check_write_is_refused(CONFIG)

    executed = [call.args[0] for call in cursor.execute.call_args_list]
    assert not any('READ ONLY' in statement for statement in executed)
