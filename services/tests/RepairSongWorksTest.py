"""Covers scripts/repair_song_works.py.

The script moves rows that are already wrong: tracks the old grouping put in a work
their key does not ask for. Two things have to hold. It must detach exactly those --
detaching a correctly grouped track is churn, missing one leaves the 117-version work
in place -- and it must not delete a work that somebody or something still points at.
"""

import importlib.util
from pathlib import Path

import pytest

from services.music_manager.tests.scripted_cursor import ScriptedCursor

pytestmark = pytest.mark.mock_base('pymysql', 'dbutils')

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'repair_song_works.py'

spec = importlib.util.spec_from_file_location('repair_song_works', SCRIPT)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def _row(track_id, title, work_key, artist='Angerfist', work_id=40, duration_secs=214.0):
    return {
        'id': track_id,
        'title': title,
        'work_key': work_key,
        'artist': artist,
        'work_id': work_id,
        'duration_secs': duration_secs,
    }


def test_a_correctly_grouped_track_is_left_alone():
    rows = [_row(1, 'Raise Your Fist (Radio Edit)', 'angerfist:::raise your fist')]
    assert repair.misfiled(rows) == []


def test_the_empty_key_group_is_emptied():
    # The whole reason the script exists: ':::' collected every title that normalizes
    # away, so all of its members are misfiled and each leaves with a key of its own.
    rows = [
        _row(1, '', ':::', artist=None, work_id=89834),
        _row(2, '🕊', ':::', artist=None, work_id=89834),
        _row(3, '᳄᳄᳄᳄᳆᳇᳇', ':::', artist=None, work_id=89834),
    ]
    wrong = repair.misfiled(rows)
    assert [row['id'] for row in wrong] == [1, 2, 3]
    assert len({row['expected_key'] for row in wrong}) == 3


def test_a_track_already_in_its_own_work_stays_there():
    # Idempotence: after the repair the sentinel key is what the work is called, so a
    # second run must find nothing.
    rows = [_row(1, '', 'track:1', artist=None, work_id=90000)]
    assert repair.misfiled(rows) == []


def test_a_collation_merged_track_is_detached():
    # utf8mb4_general_ci merged two works whose keys differ byte for byte, so the
    # loser's tracks sit under the winner's key. Recomputing the key finds them
    # without having to know which pairs collided.
    rows = [_row(1, 'Raise Your Fist', 'someone else:::raise your fist')]
    wrong = repair.misfiled(rows)
    assert [row['expected_key'] for row in wrong] == ['angerfist:::raise your fist']


def test_a_renamed_artist_is_reported_apart_from_a_wrong_grouping():
    # The recompute cannot tell a collation merge from an artist that was renamed
    # after its tracks were grouped -- in both cases the stored key is simply not the
    # key the row asks for. Re-keying is right either way, but a rename is churn
    # rather than a repair, so the report has to let the operator see the difference
    # before anything is written.
    rows = [
        _row(1, '', ':::', artist=None),
        _row(2, 'Raise Your Fist', 'angerfist old name:::raise your fist'),
    ]
    assert repair.by_reason(repair.misfiled(rows)) == {'unusable-title': 1, 'stale-key': 1}


def test_a_title_that_became_usable_leaves_its_sentinel_work():
    # The tagger filled in a title that used to be blank. The track is sitting in a
    # work named after itself and has to rejoin the song it belongs to.
    rows = [_row(1, 'Raise Your Fist', 'track:1')]
    wrong = repair.misfiled(rows)
    assert [row['reason'] for row in wrong] == ['title-became-usable']


def test_a_hand_split_track_is_never_read():
    # work_locked = 1 is excluded in SQL rather than in Python, because the worker
    # honours the same flag and the two have to agree.
    assert 'work_locked = 0' in repair._GROUPED


def test_detach_clears_the_three_columns_the_worker_writes():
    cursor = ScriptedCursor()
    repair.detach(cursor, [1, 2, 3])
    updates = cursor.statements_matching('UPDATE library_tracks')
    assert len(updates) == 1
    sql, params = updates[0]
    assert 'work_id = NULL' in sql and 'version_kind = NULL' in sql and 'version_score = NULL' in sql
    assert params == (1, 2, 3)


def test_detach_refuses_to_clear_a_track_that_was_locked_meanwhile():
    # autocommit is on, so a split can land between the read and this update. The
    # guard is in the statement rather than in Python for exactly that window.
    cursor = ScriptedCursor()
    repair.detach(cursor, [1])
    assert 'work_locked = 0' in cursor.statements_matching('UPDATE library_tracks')[0][0]


def test_detach_pages_a_long_list():
    cursor = ScriptedCursor()
    repair.detach(cursor, list(range(repair.UPDATE_CHUNK + 1)))
    assert len(cursor.statements_matching('UPDATE library_tracks')) == 2


def test_an_emptied_work_is_deleted():
    cursor = ScriptedCursor(
        [
            ('SELECT COUNT(*) AS n FROM library_tracks', (40,), {'n': 0}),
            ('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': None}),
        ]
    )
    stats = repair.settle_works(cursor, {40})
    assert stats['works_deleted'] == 1
    delete = cursor.statements_matching('DELETE w FROM library_works')[0]
    assert delete[1] == (40,)
    # Emptiness is a condition of the delete, not something read a moment earlier: the
    # worker may assign a track to this work in between, and deleting it then would
    # leave that track pointing at a work that is gone.
    assert 'LEFT JOIN library_tracks t ON t.work_id = w.id' in delete[0]
    assert 't.id IS NULL' in delete[0]


def test_a_work_that_filled_up_again_during_the_run_is_not_counted_as_deleted():
    cursor = ScriptedCursor(
        [
            ('SELECT COUNT(*) AS n FROM library_tracks', (40,), {'n': 0}),
            ('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': None}),
        ],
        rowcount=0,
    )
    stats = repair.settle_works(cursor, {40})
    assert stats['works_deleted'] == 0


def test_a_work_that_kept_members_is_recomputed_not_deleted():
    cursor = ScriptedCursor(
        [
            ('SELECT COUNT(*) AS n FROM library_tracks', (40,), {'n': 2}),
            ('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': None}),
            ('ORDER BY t.version_score DESC', (40,), {'id': 7}),
        ]
    )
    stats = repair.settle_works(cursor, {40})
    assert stats == {'works_deleted': 0, 'works_kept': 1, 'works_emptied_not_deleted': []}
    assert cursor.statements_matching('DELETE') == []
    updates = cursor.statements_matching('UPDATE library_works SET canonical_track_id')
    assert [params for _sql, params in updates] == [(7, 40)]


def test_a_pinned_work_survives_losing_its_members():
    # The pin is somebody's decision. Emptying the work is the repair; deleting it
    # would throw that decision away with nothing to show for it.
    cursor = ScriptedCursor(
        [
            ('SELECT COUNT(*) AS n FROM library_tracks', (40,), {'n': 0}),
            ('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': 9}),
        ]
    )
    stats = repair.settle_works(cursor, {40})
    assert stats['works_deleted'] == 0
    assert stats['works_emptied_not_deleted'] == [40]
    assert cursor.statements_matching('DELETE') == []


def test_a_work_another_work_points_at_survives():
    # related_work_id carries no foreign key, so nothing else would stop the delete;
    # it would just leave a dangling id behind.
    cursor = ScriptedCursor(
        [
            ('SELECT COUNT(*) AS n FROM library_tracks', (40,), {'n': 0}),
            ('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': None}),
            ('WHERE related_work_id = %s', (40,), {'id': 41}),
        ]
    )
    stats = repair.settle_works(cursor, {40})
    assert stats['works_deleted'] == 0
    assert stats['works_emptied_not_deleted'] == [40]


def test_a_work_that_no_longer_exists_is_skipped():
    cursor = ScriptedCursor([('SELECT COUNT(*) AS n FROM library_tracks', (40,), {'n': 0})])
    stats = repair.settle_works(cursor, {40})
    assert stats['works_deleted'] == 0
    assert cursor.statements_matching('DELETE') == []


def test_a_set_leaves_the_work_it_shared_with_another_episode():
    # Sixteen hour-long episodes of one show sat in one work on production. The key
    # rule changed under them, so the repair is what moves them out.
    rows = [
        _row(1, 'Andromedha Guest Mix', ':::andromedha guest mix', artist=None, duration_secs=3560.2),
        _row(2, 'Andromedha Guest Mix', ':::andromedha guest mix', artist=None, duration_secs=3629.4),
    ]
    wrong = repair.misfiled(rows)
    assert [row['reason'] for row in wrong] == ['long-form', 'long-form']
    assert len({row['expected_key'] for row in wrong}) == 2


def test_a_long_track_that_already_sits_alone_is_not_moved_again():
    # Idempotence: after the first repair the key is the sentinel, and a second run
    # must find nothing to do.
    rows = [_row(1, 'Andromedha Guest Mix', 'track:1', artist=None, duration_secs=3560.2)]
    assert repair.misfiled(rows) == []


def test_the_rescore_query_matches_a_download_on_its_whole_path():
    # The provenance test it repairs compared a basename against a column that only
    # ever holds absolute paths, so it matched nothing.
    sql = repair._MISSCORED_DOWNLOADS
    assert 'sc.filename = mf.file_path' in sql
    assert 'yt.path = mf.file_path' in sql
    assert 'work_locked = 0' in sql


# --- bug report 098: the key rules changed, the repair is the regroup ---------------------


def test_a_new_key_rule_moves_a_track_into_the_plain_titles_work():
    rows = [
        _row(1, 'Lost On You', 'dj test:::lost on you', artist='Dj Test', work_id=40),
        _row(
            2,
            'Lost On You - Official Hardcore Visualizer',
            'dj test:::lost on you official hardcore visualizer',
            artist='Dj Test',
            work_id=41,
        ),
    ]
    wrong = repair.misfiled(rows)
    assert [(row['id'], row['expected_key'], row['reason']) for row in wrong] == [
        (2, 'dj test:::lost on you', 'stale-key')
    ]


def test_the_dry_run_counts_moves_into_existing_and_new_works():
    rows = [
        _row(2, 'Lost On You - Official Video', 'dj test:::lost on you official video', artist='Dj Test', work_id=41),
        _row(3, 'Never (Official Audio)', 'dj test:::never official audio', artist='Dj Test', work_id=42),
        _row(4, 'Never (Official Music Video)', 'dj test:::never official music video', artist='Dj Test', work_id=43),
    ]
    wrong = repair.misfiled(rows)
    summary = repair.movement_summary(wrong, {'dj test:::lost on you'})
    assert summary == {
        'tracks_moving': 3,
        'into_existing_work': 1,
        'into_new_work': 2,
        'source_works': 3,
        'target_works': 2,
        'pinned_kept': 0,
    }


def test_a_pinned_track_stays_in_its_work():
    row = _row(2, 'Lost On You - Official Video', 'dj test:::lost on you official video', artist='Dj Test', work_id=41)
    row['pinned_track_id'] = 2
    wrong = repair.misfiled([row])
    assert [item['reason'] for item in wrong] == ['pinned-kept']
    assert repair.movable(wrong) == []
    assert repair.movement_summary(wrong, set())['pinned_kept'] == 1


def test_a_pin_on_another_member_does_not_hold_this_track():
    row = _row(2, 'Lost On You - Official Video', 'dj test:::lost on you official video', artist='Dj Test', work_id=41)
    row['pinned_track_id'] = 99
    assert [item['id'] for item in repair.movable(repair.misfiled([row]))] == [2]


def test_the_grouped_query_reads_the_pin():
    assert 'w.pinned_track_id' in repair._GROUPED


def test_existing_work_keys_reads_once_with_literal_sql():
    cursor = ScriptedCursor(
        [('SELECT work_key FROM library_works', None, [{'work_key': 'a:::b'}, {'work_key': 'c:::d'}])]
    )
    assert repair.existing_work_keys(cursor, ['a:::b', 'x:::y']) == {'a:::b'}
    assert cursor.executed == [('SELECT work_key FROM library_works', None)]
    assert repair.existing_work_keys(ScriptedCursor([]), []) == set()


def test_a_second_run_after_the_regroup_finds_nothing():
    rows = [_row(2, 'Lost On You - Official Video', 'dj test:::lost on you', artist='Dj Test', work_id=40)]
    assert repair.misfiled(rows) == []


def _main_with(monkeypatch, cursor, *argv):
    conn = type('Conn', (), {})()
    conn.cursor = lambda: cursor
    conn.commit = lambda: None
    conn.close = lambda: None
    monkeypatch.setattr(repair, 'get_db_connection', lambda: conn)
    monkeypatch.setattr('sys.argv', ['repair_song_works.py', *argv])
    return repair.main()


SERIES = [
    {'work_id': 90, 'work_key': 'q dance:::next', 'duration_secs': 100 + 10 * index, 'release_date': None}
    for index in range(13)
]


def test_the_dry_run_writes_nothing_and_reports_the_split(monkeypatch, capsys):
    cursor = ScriptedCursor(
        [
            ('HAVING COUNT(*) >= %s', None, SERIES),
            (
                'LEFT JOIN library_artists a',
                None,
                [
                    _row(1, 'NEXT', 'q dance:::next', artist='Q-Dance', work_id=90),
                    _row(2, 'Never (Official Audio)', 'dj test:::never official audio', artist='Dj Test', work_id=42),
                ],
            ),
        ]
    )
    assert _main_with(monkeypatch, cursor, '--dry-run', '--split-false-merges') == 0
    output = capsys.readouterr().out
    assert "work 90 [split] 'q dance:::next'" in output
    assert '"works_to_split": 1' in output
    # the series' own member is left out of the re-key count: it is about to be locked
    assert '"tracks_moving": 1' in output
    assert [sql for sql, _params in cursor.executed if sql.startswith(('UPDATE', 'DELETE', 'INSERT'))] == []


def test_the_report_only_reads(monkeypatch, capsys):
    cursor = ScriptedCursor([('HAVING COUNT(*) >= %s', None, SERIES)])
    assert _main_with(monkeypatch, cursor, '--report') == 0
    assert '"suspicious_works": 1' in capsys.readouterr().out
    assert all(sql.startswith(('SELECT', 'WITH')) for sql, _params in cursor.executed)
