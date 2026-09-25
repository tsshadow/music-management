"""What happens to a track row a retag left behind (bug report 042).

A retag that changes the title or the primary artist gives the file a new track_uid and so a new
track row. These tests pin down what `relink_track` carries over and what it refuses to touch, and
how `relink_orphaned_tracks` picks the successor of a row orphaned before the fix. The SQL itself
runs against MariaDB in tests/integration/test_track_relink.py.
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from services.music_manager import track_relink
from services.music_manager.tests.scripted_cursor import ScriptedCursor

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils')

OLD, NEW = 2, 5
TRACKS = [
    {'id': OLD, 'track_uid': 'uid-old', 'work_id': None},
    {'id': NEW, 'track_uid': 'uid-new', 'work_id': None},
]
RATINGS = "FROM rating_tracks WHERE entity_type = 'track' AND entity_id = %s"


def cursor_with(*rules):
    """A cursor where the old track has no file left and both track rows exist."""
    return ScriptedCursor(
        [
            ('FROM library_media_files WHERE track_id = %s LIMIT 1', (OLD,), None),
            ('FROM library_tracks WHERE id IN', None, TRACKS),
            *rules,
        ]
    )


class RelinkRefusesTest(unittest.TestCase):
    def test_a_track_is_never_relinked_onto_itself(self):
        cursor = cursor_with()
        self.assertIsNone(track_relink.relink_track(cursor, OLD, OLD))
        self.assertEqual(cursor.executed, [])

    def test_a_track_that_still_has_a_file_is_left_alone(self):
        # Two files on one track and only one of them moved: the other still makes it a track.
        cursor = ScriptedCursor([('FROM library_media_files WHERE track_id = %s LIMIT 1', (OLD,), {'present': 1})])
        self.assertIsNone(track_relink.relink_track(cursor, OLD, NEW))
        self.assertEqual(cursor.statements_matching('DELETE'), [])
        self.assertEqual(cursor.statements_matching('UPDATE'), [])

    def test_a_missing_track_row_writes_nothing(self):
        cursor = ScriptedCursor([('FROM library_tracks WHERE id IN', None, TRACKS[:1])])
        self.assertIsNone(track_relink.relink_track(cursor, OLD, NEW))
        self.assertEqual(cursor.statements_matching('DELETE'), [])


class RelinkRatingsTest(unittest.TestCase):
    def test_a_rating_moves_to_the_new_uid_keeping_its_timestamp(self):
        cursor = cursor_with(
            (RATINGS, ('uid-old',), [{'id': 11, 'username': 'user', 'rating': 5, 'updated_at': datetime(2026, 1, 1)}]),
        )
        counts = track_relink.relink_track(cursor, OLD, NEW)

        self.assertEqual(counts['ratings_moved'], 1)
        sql, params = cursor.statements_matching('UPDATE rating_tracks SET entity_id')[0]
        self.assertIn('updated_at = updated_at', sql)
        self.assertEqual(params, ('uid-new', 11))

    def test_on_a_conflict_the_newer_rating_wins(self):
        cursor = cursor_with(
            (RATINGS, ('uid-old',), [{'id': 11, 'username': 'user', 'rating': 5, 'updated_at': datetime(2026, 9, 1)}]),
            (RATINGS, ('uid-new',), [{'id': 12, 'username': 'user', 'rating': 2, 'updated_at': datetime(2026, 1, 1)}]),
        )
        counts = track_relink.relink_track(cursor, OLD, NEW)

        self.assertEqual(counts['ratings_merged'], 1)
        _sql, params = cursor.statements_matching('UPDATE rating_tracks SET rating')[0]
        self.assertEqual(params, (5, datetime(2026, 9, 1), 12))
        self.assertEqual(cursor.statements_matching('DELETE FROM rating_tracks')[0][1], (11,))

    def test_on_a_conflict_an_older_rating_is_dropped(self):
        cursor = cursor_with(
            (RATINGS, ('uid-old',), [{'id': 11, 'username': 'user', 'rating': 5, 'updated_at': None}]),
            (RATINGS, ('uid-new',), [{'id': 12, 'username': 'user', 'rating': 2, 'updated_at': datetime(2026, 1, 1)}]),
        )
        track_relink.relink_track(cursor, OLD, NEW)

        self.assertEqual(cursor.statements_matching('UPDATE rating_tracks'), [])
        self.assertEqual(cursor.statements_matching('DELETE FROM rating_tracks')[0][1], (11,))

    def test_another_users_rating_is_not_a_conflict(self):
        cursor = cursor_with(
            (RATINGS, ('uid-old',), [{'id': 11, 'username': 'user', 'rating': 5, 'updated_at': None}]),
            (RATINGS, ('uid-new',), [{'id': 12, 'username': 'anna', 'rating': 2, 'updated_at': None}]),
        )
        counts = track_relink.relink_track(cursor, OLD, NEW)
        self.assertEqual((counts['ratings_moved'], counts['ratings_merged']), (1, 0))


class RelinkListensAndRestTest(unittest.TestCase):
    def test_listens_move_without_touching_listened_at_and_duplicates_go(self):
        cursor = cursor_with()
        track_relink.relink_track(cursor, OLD, NEW)

        sql, params = cursor.statements_matching('UPDATE IGNORE scrobble_listens')[0]
        self.assertIn('listened_at = listened_at', sql)
        self.assertEqual(params, (NEW, OLD))
        self.assertEqual(cursor.statements_matching('DELETE FROM scrobble_listens')[0][1], (OLD,))

    def test_analysis_rows_follow_the_track(self):
        cursor = cursor_with()
        track_relink.relink_track(cursor, OLD, NEW)

        self.assertEqual(
            cursor.statements_matching('UPDATE library_track_audio_features SET internal_track_id')[0][1], (NEW, OLD)
        )
        self.assertEqual(
            cursor.statements_matching('UPDATE IGNORE library_track_ml_labels SET track_id')[0][1],
            ('uid-new', 'uid-old'),
        )

    def test_the_old_row_is_deleted_after_everything_moved(self):
        cursor = cursor_with()
        counts = track_relink.relink_track(cursor, OLD, NEW)

        self.assertEqual(counts['tracks_deleted'], 1)
        statements = [sql for sql, _p in cursor.executed]
        deleted_at = statements.index('DELETE FROM library_tracks WHERE id = %s')
        moved_at = next(i for i, sql in enumerate(statements) if 'scrobble_listens' in sql)
        self.assertLess(moved_at, deleted_at)

    def test_a_pin_follows_the_file_and_a_computed_canonical_is_recomputed(self):
        cursor = cursor_with(
            (
                'FROM library_works WHERE canonical_track_id = %s OR pinned_track_id = %s',
                None,
                [{'id': 40, 'pinned_track_id': OLD}, {'id': 41, 'pinned_track_id': None}],
            ),
        )
        with patch.object(track_relink, 'recompute_canonicals') as recompute:
            track_relink.relink_track(cursor, OLD, NEW)

        self.assertEqual(cursor.statements_matching('SET pinned_track_id = %s')[0][1], (NEW, OLD))
        self.assertEqual(cursor.statements_matching('SET canonical_track_id = NULL')[0][1], (OLD,))
        # The pinned work waits for the worker, which assigns the new track first.
        recompute.assert_called_once_with(cursor, {41})

    def test_no_work_means_no_recompute(self):
        with patch.object(track_relink, 'recompute_canonicals') as recompute:
            track_relink.relink_track(cursor_with(), OLD, NEW)
        recompute.assert_not_called()


ORPHAN = {'id': OLD, 'title': 'Raise Your Fist', 'duration_secs': 300.0, 'primary_artist_id': 7}
CANDIDATES = 'AND ABS(t.duration_secs - %s) < %s'


class FindTargetTest(unittest.TestCase):
    def test_the_one_track_with_the_same_title_and_primary_artist_is_the_target(self):
        cursor = ScriptedCursor(
            [(CANDIDATES, None, [{'id': NEW, 'title': 'Raise your fist!', 'primary_artist_id': 7}])]
        )
        self.assertEqual(track_relink.find_relink_target(cursor, ORPHAN), NEW)

    def test_two_candidates_are_not_guessed_between(self):
        cursor = ScriptedCursor(
            [
                (
                    CANDIDATES,
                    None,
                    [
                        {'id': NEW, 'title': 'Raise Your Fist', 'primary_artist_id': 7},
                        {'id': 9, 'title': 'Raise Your Fist', 'primary_artist_id': 7},
                    ],
                )
            ]
        )
        self.assertIsNone(track_relink.find_relink_target(cursor, ORPHAN))

    def test_a_different_title_is_not_a_match(self):
        cursor = ScriptedCursor(
            [(CANDIDATES, None, [{'id': NEW, 'title': 'Dance with the Wolves', 'primary_artist_id': 7}])]
        )
        self.assertIsNone(track_relink.find_relink_target(cursor, ORPHAN))

    def test_reordered_credits_match_on_the_same_artist_set(self):
        cursor = ScriptedCursor(
            [
                (CANDIDATES, None, [{'id': NEW, 'title': 'Raise Your Fist', 'primary_artist_id': 8}]),
                ('FROM library_track_artists WHERE track_id = %s', (OLD,), [{'artist_id': 7}, {'artist_id': 8}]),
                ('FROM library_track_artists WHERE track_id = %s', (NEW,), [{'artist_id': 8}, {'artist_id': 7}]),
            ]
        )
        self.assertEqual(track_relink.find_relink_target(cursor, ORPHAN), NEW)

    def test_a_different_artist_set_is_not_a_match(self):
        cursor = ScriptedCursor(
            [
                (CANDIDATES, None, [{'id': NEW, 'title': 'Raise Your Fist', 'primary_artist_id': 8}]),
                ('FROM library_track_artists WHERE track_id = %s', (OLD,), [{'artist_id': 7}]),
                ('FROM library_track_artists WHERE track_id = %s', (NEW,), [{'artist_id': 8}, {'artist_id': 7}]),
            ]
        )
        self.assertIsNone(track_relink.find_relink_target(cursor, ORPHAN))

    def test_an_orphan_without_duration_or_artist_is_not_matched(self):
        cursor = ScriptedCursor()
        self.assertIsNone(track_relink.find_relink_target(cursor, ORPHAN | {'duration_secs': None}))
        self.assertIsNone(track_relink.find_relink_target(cursor, ORPHAN | {'primary_artist_id': None}))
        self.assertEqual(cursor.executed, [])


class RelinkOrphansTest(unittest.TestCase):
    def _conn(self, cursor):
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_each_matched_orphan_is_its_own_transaction(self):
        cursor = ScriptedCursor([('WHERE NOT EXISTS (SELECT 1 FROM library_media_files', None, [ORPHAN])])
        conn = self._conn(cursor)
        counts = track_relink.empty_counts() | {'ratings_moved': 2, 'tracks_deleted': 1}
        with (
            patch.object(track_relink, 'find_relink_target', return_value=NEW),
            patch.object(track_relink, 'relink_track', return_value=counts) as relink,
        ):
            totals = track_relink.relink_orphaned_tracks(conn)

        relink.assert_called_once_with(cursor, OLD, NEW)
        conn.begin.assert_called_once()
        conn.commit.assert_called_once()
        self.assertEqual((totals['orphans'], totals['relinked'], totals['ratings_moved']), (1, 1, 2))

    def test_an_unmatched_orphan_is_counted_and_left(self):
        cursor = ScriptedCursor([('WHERE NOT EXISTS (SELECT 1 FROM library_media_files', None, [ORPHAN])])
        conn = self._conn(cursor)
        with patch.object(track_relink, 'find_relink_target', return_value=None):
            totals = track_relink.relink_orphaned_tracks(conn)
        conn.begin.assert_not_called()
        self.assertEqual(totals['unmatched'], 1)

    def test_a_failing_orphan_is_rolled_back_and_the_rest_continue(self):
        second = ORPHAN | {'id': 3}
        cursor = ScriptedCursor([('WHERE NOT EXISTS (SELECT 1 FROM library_media_files', None, [ORPHAN, second])])
        conn = self._conn(cursor)
        with (
            patch.object(track_relink, 'find_relink_target', return_value=NEW),
            patch.object(
                track_relink, 'relink_track', side_effect=[RuntimeError('lock wait'), track_relink.empty_counts()]
            ),
        ):
            totals = track_relink.relink_orphaned_tracks(conn)
        conn.rollback.assert_called_once()
        self.assertEqual((totals['failed'], totals['relinked']), (1, 1))


if __name__ == '__main__':
    unittest.main()
