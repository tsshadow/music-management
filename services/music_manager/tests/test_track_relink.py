"""What happens to a track row a retag left behind (bug report 042).

A retag that changes the title or the primary artist gives the file a new track_uid and so a new
track row. These tests pin down what `relink_track` carries over and what it refuses to touch, and
how `relink_orphaned_tracks` picks the successor of a row orphaned before the fix. The SQL itself
runs against MariaDB in tests/integration/test_track_relink.py.
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from services.music_manager import track_relink
from services.music_manager.tests.scripted_cursor import ScriptedCursor

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


STUB = {'id': 30, 'title': '04-lucy_furr_and_meander_-_damnation', 'duration_secs': None, 'primary_artist_id': None}
ORPHANS_SQL = 'WHERE NOT EXISTS (SELECT 1 FROM library_media_files'
MEDIA_SQL = "SUBSTRING_INDEX(file_path, '/', -1) AS file_name"


class FileStemTest(unittest.TestCase):
    def test_the_last_extension_and_the_directory_go(self):
        self.assertEqual(track_relink.file_stem('/music/a/04-x_-_y.mp3'), '04-x_-_y')
        self.assertEqual(track_relink.file_stem('04-x.y.flac'), '04-x.y')

    def test_a_name_without_an_extension_or_a_dotfile_is_kept_whole(self):
        self.assertEqual(track_relink.file_stem('/music/README'), 'README')
        self.assertEqual(track_relink.file_stem('/music/.hidden'), '.hidden')
        self.assertEqual(track_relink.file_stem(None), '')


class FileNameIndexTest(unittest.TestCase):
    def test_only_stems_an_orphan_could_match_are_kept(self):
        cursor = ScriptedCursor(
            [
                (
                    MEDIA_SQL,
                    None,
                    [
                        {'track_id': 7, 'file_name': 'a.mp3'},
                        {'track_id': 8, 'file_name': 'a.flac'},
                        {'track_id': 9, 'file_name': 'b.mp3'},
                    ],
                )
            ]
        )
        self.assertEqual(track_relink.build_file_name_index(cursor, {'a'}), {'a': {7, 8}})

    def test_no_titles_means_no_query(self):
        cursor = ScriptedCursor()
        self.assertEqual(track_relink.build_file_name_index(cursor, set()), {})
        self.assertEqual(cursor.executed, [])


class FindFileNameTargetTest(unittest.TestCase):
    def test_one_track_with_that_file_name_is_the_target(self):
        index = {STUB['title']: {NEW}}
        self.assertEqual(track_relink.find_file_name_target(index, STUB), (NEW, False))

    def test_two_files_of_the_same_track_are_still_one_successor(self):
        # The index holds track ids, so an mp3 beside its flac collapses into one.
        index = track_relink.build_file_name_index(
            ScriptedCursor(
                [
                    (
                        MEDIA_SQL,
                        None,
                        [
                            {'track_id': NEW, 'file_name': f"{STUB['title']}.mp3"},
                            {'track_id': NEW, 'file_name': f"{STUB['title']}.flac"},
                        ],
                    )
                ]
            ),
            {STUB['title']},
        )
        self.assertEqual(track_relink.find_file_name_target(index, STUB), (NEW, False))

    def test_several_tracks_are_ambiguous_and_not_guessed(self):
        index = {STUB['title']: {NEW, 9}}
        self.assertEqual(track_relink.find_file_name_target(index, STUB), (None, True))

    def test_the_orphan_itself_is_never_its_own_target(self):
        index = {STUB['title']: {STUB['id']}}
        self.assertEqual(track_relink.find_file_name_target(index, STUB), (None, False))
        index = {STUB['title']: {STUB['id'], NEW}}
        self.assertEqual(track_relink.find_file_name_target(index, STUB), (NEW, False))

    def test_the_title_is_compared_exactly(self):
        index = {STUB['title'].upper(): {NEW}}
        self.assertEqual(track_relink.find_file_name_target(index, STUB), (None, False))
        self.assertEqual(track_relink.find_file_name_target(index, STUB | {'title': None}), (None, False))


class RelinkOrphansByFileNameTest(unittest.TestCase):
    def _conn(self, orphans, files):
        cursor = ScriptedCursor([(ORPHANS_SQL, None, orphans), (MEDIA_SQL, None, files)])
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn, cursor

    def test_a_unique_file_name_relinks_the_stub(self):
        conn, cursor = self._conn([STUB], [{'track_id': NEW, 'file_name': f"{STUB['title']}.mp3"}])
        counts = track_relink.empty_counts() | {'tracks_deleted': 1}
        with patch.object(track_relink, 'relink_track', return_value=counts) as relink:
            totals = track_relink.relink_orphaned_tracks(conn)
        relink.assert_called_once_with(cursor, STUB['id'], NEW)
        self.assertEqual(
            (totals['relinked'], totals['relinked_file_name'], totals['relinked_metadata'], totals['unmatched']),
            (1, 1, 0, 0),
        )

    def test_an_ambiguous_file_name_is_left_and_counted(self):
        files = [
            {'track_id': NEW, 'file_name': f"{STUB['title']}.mp3"},
            {'track_id': 9, 'file_name': f"{STUB['title']}.mp3"},
        ]
        conn, _cursor = self._conn([STUB], files)
        with patch.object(track_relink, 'relink_track') as relink:
            totals = track_relink.relink_orphaned_tracks(conn)
        relink.assert_not_called()
        conn.begin.assert_not_called()
        self.assertEqual((totals['unmatched'], totals['ambiguous_file_name'], totals['relinked']), (1, 1, 0))

    def test_a_metadata_match_wins_over_the_file_name(self):
        # The orphan's title is also some other track's file name: the metadata successor is used.
        conn, cursor = self._conn([ORPHAN], [{'track_id': 9, 'file_name': f"{ORPHAN['title']}.mp3"}])
        with (
            patch.object(track_relink, 'find_relink_target', return_value=NEW),
            patch.object(track_relink, 'relink_track', return_value=track_relink.empty_counts()) as relink,
        ):
            totals = track_relink.relink_orphaned_tracks(conn)
        relink.assert_called_once_with(cursor, OLD, NEW)
        self.assertEqual((totals['relinked_metadata'], totals['relinked_file_name']), (1, 0))

    def test_a_dry_run_counts_per_key_and_writes_nothing(self):
        orphans = [ORPHAN, STUB, STUB | {'id': 31, 'title': 'nothing-like-it'}]
        conn, cursor = self._conn(orphans, [{'track_id': NEW, 'file_name': f"{STUB['title']}.mp3"}])
        with (
            patch.object(track_relink, 'find_relink_target', side_effect=[NEW, None, None]),
            patch.object(track_relink, 'relink_track') as relink,
        ):
            totals = track_relink.relink_orphaned_tracks(conn, dry_run=True)
        relink.assert_not_called()
        conn.begin.assert_not_called()
        conn.commit.assert_not_called()
        self.assertEqual([sql for sql, _p in cursor.executed if not sql.startswith('SELECT')], [])
        self.assertTrue(totals['dry_run'])
        self.assertEqual(
            (
                totals['orphans'],
                totals['relinked'],
                totals['relinked_metadata'],
                totals['relinked_file_name'],
                totals['unmatched'],
            ),
            (3, 2, 1, 1, 1),
        )

    def test_progress_is_written_into_the_given_dict(self):
        conn, _cursor = self._conn([STUB], [])
        progress = {}
        returned = track_relink.relink_orphaned_tracks(conn, dry_run=True, totals=progress)
        self.assertIs(returned, progress)
        self.assertEqual(progress['unmatched'], 1)


if __name__ == '__main__':
    unittest.main()


class MetadataIndexTest(unittest.TestCase):
    """Bug report 107: the bulk run reads the candidates once instead of one query per orphan."""

    def _row(self, track_id, title='Hated', duration=200.0, artist=5):
        return {'id': track_id, 'title': title, 'duration_secs': duration, 'primary_artist_id': artist}

    def _index(self, rows, titles):
        cursor = ScriptedCursor([('FROM library_tracks t WHERE t.duration_secs IS NOT NULL', None, rows)])
        return track_relink.build_metadata_index(cursor, titles)

    def test_only_titles_an_orphan_carries_are_indexed(self):
        index = self._index([self._row(1), self._row(2, title='Other')], {'hated'})
        self.assertEqual([row['id'] for row in index['hated']], [1])
        self.assertNotIn('other', index)

    def test_same_title_duration_and_artist_is_the_target_without_a_query(self):
        orphan = self._row(10)
        index = self._index([self._row(11)], {'hated'})
        cursor = ScriptedCursor()
        self.assertEqual(track_relink.find_relink_target(cursor, orphan, index), 11)
        self.assertEqual(cursor.executed, [])

    def test_a_different_duration_or_the_orphan_itself_is_no_candidate(self):
        orphan = self._row(10)
        index = self._index([self._row(10), self._row(12, duration=203.0)], {'hated'})
        self.assertIsNone(track_relink.find_relink_target(ScriptedCursor(), orphan, index))

    def test_two_matches_are_not_guessed_at(self):
        orphan = self._row(10)
        index = self._index([self._row(11), self._row(12)], {'hated'})
        self.assertIsNone(track_relink.find_relink_target(ScriptedCursor(), orphan, index))

    def test_reordered_credits_match_through_the_artist_sets(self):
        orphan = self._row(10, artist=5)
        index = self._index([self._row(11, artist=6)], {'hated'})
        cursor = ScriptedCursor(
            [
                ('FROM library_track_artists WHERE track_id', (10,), [{'artist_id': 5}, {'artist_id': 6}]),
                ('FROM library_track_artists WHERE track_id', (11,), [{'artist_id': 6}, {'artist_id': 5}]),
            ]
        )
        self.assertEqual(track_relink.find_relink_target(cursor, orphan, index), 11)

    def test_an_artist_the_orphan_never_credited_is_no_candidate(self):
        orphan = self._row(10, artist=5)
        index = self._index([self._row(11, artist=9)], {'hated'})
        cursor = ScriptedCursor([('FROM library_track_artists WHERE track_id', (10,), [{'artist_id': 5}])])
        self.assertIsNone(track_relink.find_relink_target(cursor, orphan, index))

    def test_the_bulk_run_passes_the_index(self):
        cursor = ScriptedCursor([(ORPHANS_SQL, None, [ORPHAN])])
        conn = MagicMock()
        conn.cursor.return_value = cursor
        with patch.object(track_relink, 'find_relink_target', return_value=None) as find:
            track_relink.relink_orphaned_tracks(conn, dry_run=True)
        self.assertIsInstance(find.call_args.args[2], dict)
