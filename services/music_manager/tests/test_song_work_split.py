"""The SQL half of the false-merge guard: split_work and split_false_merges.

Pure detection is pinned in test_song_work_audit.py. Here the question is what the worker
writes: every unlocked member to a locked `split:` work of its own, a pin that named a
departed member cleared, and nothing at all for a work that looks like one song.
"""

from services.music_manager import song_version_worker as worker
from services.music_manager.tests.scripted_cursor import ScriptedCursor

MEMBERS = [
    {'id': 11, 'title': 'NEXT', 'primary_artist_id': 5},
    {'id': 12, 'title': 'NEXT', 'primary_artist_id': 5},
]


def _split_rules(durations):
    return [
        ('HAVING COUNT(*) > %s', (12,), [{'work_id': 90}, {'work_id': 77}]),
        (
            'SELECT duration_secs, release_date FROM library_tracks',
            (90,),
            [{'duration_secs': value, 'release_date': None} for value in durations],
        ),
        ('WHERE work_id = %s AND work_locked = 0 ORDER BY id', (90,), MEMBERS),
        ('SELECT id FROM library_works WHERE work_key = %s', ('split:11',), {'id': 501}),
        ('SELECT id FROM library_works WHERE work_key = %s', ('split:12',), {'id': 502}),
    ]


def test_a_series_is_split_into_locked_works():
    cursor = ScriptedCursor(_split_rules([100 + 10 * index for index in range(13)]))
    result = worker.split_false_merges(cursor, {90, 91})

    assert result == {90: [11, 12]}
    inserts = cursor.statements_matching('INSERT INTO library_works')
    assert [params[0] for _sql, params in inserts] == ['split:11', 'split:12']
    moves = cursor.statements_matching('SET work_id = %s, work_locked = 1')
    assert [params for _sql, params in moves] == [(501, 11, 90), (502, 12, 90)]
    # the precondition travels with the write
    assert all('AND work_id = %s AND work_locked = 0' in sql for sql, _params in moves)
    # the old work's canonical is recomputed, which is what clears a pin that left with them
    assert ('SELECT pinned_track_id FROM library_works WHERE id = %s', (90,)) in cursor.executed
    # a large work that was not touched this pass is not read at all
    assert cursor.statements_matching('WHERE work_id = %s AND work_locked = 0 ORDER BY id')[0][1] == (90,)
    assert not [params for _sql, params in cursor.executed if params == (77,)]


def test_a_work_that_looks_like_one_song_is_left_alone():
    # 13 members but only two lengths: a popular song, not a series.
    cursor = ScriptedCursor(_split_rules([205] * 7 + [330] * 6))
    assert worker.split_false_merges(cursor, {90}) == {}
    assert cursor.statements_matching('INSERT INTO library_works') == []
    assert cursor.statements_matching('UPDATE') == []


def test_a_suspicious_but_ambiguous_work_is_not_split():
    cursor = ScriptedCursor(_split_rules([100 + 10 * index for index in range(12)] + [100]))
    assert worker.split_false_merges(cursor, {90}) == {}


def test_no_touched_works_means_no_queries():
    cursor = ScriptedCursor([])
    assert worker.split_false_merges(cursor, set()) == {}
    assert cursor.executed == []


def test_the_count_query_is_literal_and_asks_for_more_members_than_the_threshold():
    cursor = ScriptedCursor([])
    worker.split_false_merges(cursor, {3, 1, 2})
    sql, params = cursor.executed[0]
    assert 'HAVING COUNT(*) > %s' in sql
    assert ' IN (' not in sql
    assert params == (12,)


def test_a_track_that_moved_meanwhile_is_not_counted():
    rules = _split_rules([100 + 10 * index for index in range(13)])
    cursor = ScriptedCursor(rules, rowcount=0)
    assert worker.split_false_merges(cursor, {90}) == {}
    assert cursor.statements_matching('SELECT pinned_track_id FROM library_works') == []


def test_find_suspicious_works_reports_the_series():
    rows = [
        {'work_id': 90, 'work_key': 'q dance:::next', 'duration_secs': 100 + 10 * index, 'release_date': None}
        for index in range(13)
    ]
    cursor = ScriptedCursor([('HAVING COUNT(*) >= %s', (4,), rows)])
    found = worker.find_suspicious_works(cursor)
    assert [(work['work_id'], work['verdict']) for work in found] == [(90, 'split')]
