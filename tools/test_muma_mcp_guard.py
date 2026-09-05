"""The SQL guard in tools/muma_mcp/guard.py.

The guard is the second line of defence -- the database grant is the first -- but
it is the line that produces a usable error message, and the one whose failure
modes are subtle. The cases that matter are the ones where the statement is
*disguised*: hidden behind a comment, or hiding structure inside a string.
"""

from __future__ import annotations

import pytest

from tools.muma_mcp.guard import QueryRejected, check


@pytest.mark.parametrize(
    'sql',
    [
        'SELECT 1',
        'select id from library_tracks limit 5',
        '  WITH t AS (SELECT 1) SELECT * FROM t  ',
        'SHOW TABLES',
        'DESCRIBE library_tracks',
        'DESC library_tracks',
        'EXPLAIN SELECT * FROM library_tracks',
        '(SELECT 1)',
        'SELECT 1;',
    ],
)
def test_accepts_read_statements(sql):
    assert check(sql)


@pytest.mark.parametrize(
    'sql',
    [
        'DELETE FROM library_tracks',
        'UPDATE library_tracks SET title = "x"',
        'INSERT INTO library_tracks (id) VALUES (1)',
        'DROP TABLE library_tracks',
        'TRUNCATE library_tracks',
        'ALTER TABLE library_tracks ADD COLUMN x INT',
        'CREATE TABLE x (id INT)',
        'GRANT ALL ON *.* TO nobody',
        'SET GLOBAL max_connections = 1',
        'CALL some_procedure()',
    ],
)
def test_rejects_writes_and_everything_else(sql):
    with pytest.raises(QueryRejected):
        check(sql)


def test_rejects_stacked_statements():
    with pytest.raises(QueryRejected, match='meerdere statements'):
        check('SELECT 1; DELETE FROM library_tracks')


def test_a_trailing_semicolon_is_stripped_not_rejected():
    assert check('SELECT 1;  ') == 'SELECT 1'


def test_comment_cannot_disguise_the_keyword():
    """`/* x */ DELETE` must be read as DELETE, not as a comment."""
    with pytest.raises(QueryRejected, match='DELETE'):
        check('/* SELECT */ DELETE FROM library_tracks')


def test_line_comment_cannot_hide_a_second_statement():
    with pytest.raises(QueryRejected, match='meerdere statements'):
        check('SELECT 1 -- harmless\n; DROP TABLE library_tracks')


def test_executable_comment_is_removed_before_running():
    """MariaDB *executes* /*! ... */, so the guard strips it rather than trusting it.

    The returned text is what runs, and it must no longer contain the payload.
    """
    executed = check('SELECT 1 /*!00000 , (SELECT 2) */')
    assert 'SELECT 2' not in executed


def test_comment_only_query_is_rejected():
    with pytest.raises(QueryRejected, match='commentaar'):
        check('-- niets hier\n')


def test_semicolon_inside_a_string_is_not_a_statement_separator():
    assert check("SELECT 'a; b' AS x")


def test_double_dash_without_whitespace_is_arithmetic_not_a_comment():
    assert check('SELECT 1--1')


def test_rejects_into_outfile():
    with pytest.raises(QueryRejected, match='OUTFILE'):
        check("SELECT * FROM library_tracks INTO OUTFILE '/tmp/x'")


def test_outfile_inside_a_string_literal_is_data_not_syntax():
    assert check("SELECT 'INTO OUTFILE /tmp/x' AS harmless")


@pytest.mark.parametrize('sql', ['', '   ', ';', ';SELECT 1'])
def test_rejects_empty_and_leading_separator(sql):
    with pytest.raises(QueryRejected):
        check(sql)


def test_escaped_quote_does_not_end_the_literal():
    """A backslash-escaped quote keeps the scanner inside the string."""
    assert check("SELECT 'it\\'s fine; really' AS x")


def test_doubled_quote_does_not_end_the_literal():
    assert check("SELECT 'it''s fine; really' AS x")
