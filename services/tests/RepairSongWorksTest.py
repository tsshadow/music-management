"""Covers scripts/repair_song_works.py.

The script moves rows that are already wrong: tracks the old grouping put in a work
their key does not ask for. Two things have to hold. It must detach exactly those --
detaching a correctly grouped track is churn, missing one leaves the 117-version work
in place -- and it must not delete a work that somebody or something still points at.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.music_manager.tests.scripted_cursor import ScriptedCursor

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'repair_song_works.py'

spec = importlib.util.spec_from_file_location('repair_song_works', SCRIPT)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def _row(track_id, title, work_key, artist='Angerfist', work_id=40):
    return {'id': track_id, 'title': title, 'work_key': work_key, 'artist': artist, 'work_id': work_id}


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
