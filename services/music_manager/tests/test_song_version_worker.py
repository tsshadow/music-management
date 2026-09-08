"""The SQL half of song versions: grouping tracks under works and choosing the canonical.

The ranking rules are pinned in test_song_versions.py against pure functions.
What this module has to get right is narrower and easier to get wrong quietly:
that a track with several files is scored on its best one rather than its last,
that a pin beats the score, that a recompute for a work that no longer exists
does nothing rather than writing NULL somewhere, and that one pass touches
exactly the works it changed.

Every test runs against a ScriptedCursor. The worker is a background loop over a
real database in production, and tests/integration is where the SQL meets a
schema; here it meets a script, so what is asserted is the statements it issued.
"""

import sys
import unittest
from unittest.mock import MagicMock

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.music_manager import song_version_worker as worker
from services.music_manager.song_versions import version_score
from services.music_manager.tests.scripted_cursor import ScriptedCursor

# Seconds and bytes chosen so the derived bitrate lands in different tiers: the
# FLAC is a lossless-sized file, the MP3 a 128k one.
FLAC = {'file_path': '/mnt/music/a.flac', 'file_size': 30_000_000, 'duration_secs': 300}
MP3 = {'file_path': '/mnt/music/a.mp3', 'file_size': 4_800_000, 'duration_secs': 300}


def _row(track_id, title, artist='Angerfist', files=MP3, has_label=1, from_soundcloud=0, from_youtube=0):
    return {
        'id': track_id,
        'title': title,
        'artist': artist,
        'has_label': has_label,
        'from_soundcloud': from_soundcloud,
        'from_youtube': from_youtube,
        **files,
    }


class RankRowTest(unittest.TestCase):
    def test_a_labelled_release_that_was_not_downloaded_is_official(self):
        kind, score = worker._rank_row(_row(1, 'Raise Your Fist (Extended Mix)'))
        self.assertEqual(kind, 'extended')
        self.assertEqual(score, version_score(True, 'extended', MP3['file_path'], 128))

    def test_a_labelled_track_from_soundcloud_is_not_official(self):
        # The label join alone would call a SoundCloud rip official whenever the
        # tagger managed to attach a label to it; the archive membership is what
        # says where the bytes came from.
        _kind, official = worker._rank_row(_row(1, 'Raise Your Fist'))
        _kind, ripped = worker._rank_row(_row(1, 'Raise Your Fist', from_soundcloud=1))
        self.assertGreater(official, ripped)

    def test_a_track_without_a_file_still_ranks(self):
        kind, score = worker._rank_row(
            _row(1, 'Raise Your Fist', files={'file_path': None, 'file_size': None, 'duration_secs': None})
        )
        # No version suffix is the plain recording, which the ranking calls 'none'.
        self.assertEqual(kind, 'none')
        self.assertIsInstance(score, int)


class BestPerTrackTest(unittest.TestCase):
    def test_a_track_with_two_files_is_scored_on_its_best_one(self):
        # The join returns the track once per file, MP3 first. Without the
        # per-track reduction the FLAC row would simply overwrite the MP3 row,
        # which happens to be right here -- so the order is reversed to make the
        # last-row-wins failure visible.
        rows = [_row(1, 'Raise Your Fist', files=FLAC), _row(1, 'Raise Your Fist', files=MP3)]
        best = worker._best_per_track(rows)
        self.assertEqual(list(best), [1])
        self.assertEqual(best[1]['row']['file_path'], FLAC['file_path'])

    def test_different_tracks_stay_separate(self):
        best = worker._best_per_track([_row(1, 'One'), _row(2, 'Two')])
        self.assertEqual(sorted(best), [1, 2])

    def test_no_rows_means_no_candidates(self):
        self.assertEqual(worker._best_per_track([]), {})


class AssignWorksTest(unittest.TestCase):
    def test_two_versions_of_one_song_land_in_one_work(self):
        rows = [
            _row(1, 'Raise Your Fist (Extended Mix)'),
            _row(2, 'Raise Your Fist (Radio Edit)'),
        ]
        cursor = ScriptedCursor(
            [
                ('AS batch', None, rows),
                ('SELECT id FROM library_works WHERE work_key', None, {'id': 40}),
            ]
        )
        touched, assigned = worker.assign_works(cursor, limit=10)

        self.assertEqual(assigned, 2)
        self.assertEqual(touched, {40})
        inserts = cursor.statements_matching('INSERT INTO library_works')
        # One insert per track, both with the same key: the ON DUPLICATE KEY
        # clause is what turns the second into a lookup of the first.
        self.assertEqual(len(inserts), 2)
        self.assertEqual({params[0] for _sql, params in inserts}, {inserts[0][1][0]})
        self.assertIn('ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)', inserts[0][0])

        updates = cursor.statements_matching('UPDATE library_tracks SET work_id')
        self.assertEqual([params[0] for _sql, params in updates], [40, 40])
        self.assertEqual([params[1] for _sql, params in updates], ['extended', 'radio'])
        self.assertEqual([params[3] for _sql, params in updates], [1, 2])

    def test_a_track_with_two_files_is_assigned_once(self):
        rows = [_row(1, 'Raise Your Fist', files=MP3), _row(1, 'Raise Your Fist', files=FLAC)]
        cursor = ScriptedCursor(
            [
                ('AS batch', None, rows),
                ('SELECT id FROM library_works WHERE work_key', None, {'id': 40}),
            ]
        )
        _touched, assigned = worker.assign_works(cursor, limit=10)
        self.assertEqual(assigned, 1)
        updates = cursor.statements_matching('UPDATE library_tracks SET work_id')
        self.assertEqual(len(updates), 1)
        # Scored on the FLAC, whichever row came last.
        self.assertEqual(updates[0][1][2], worker._rank_row(rows[1])[1])

    def test_the_limit_is_passed_through(self):
        cursor = ScriptedCursor([('AS batch', None, [])])
        touched, assigned = worker.assign_works(cursor, limit=7)
        self.assertEqual((touched, assigned), (set(), 0))
        self.assertEqual(cursor.statements_matching('AS batch')[0][1], (7,))

    def test_the_query_excludes_locked_tracks(self):
        # A split track is locked so the next pass cannot put it back; the
        # ungrouped query has to honour that or the split silently undoes itself.
        cursor = ScriptedCursor([('AS batch', None, [])])
        worker.assign_works(cursor)
        sql = cursor.statements_matching('AS batch')[0][0]
        self.assertIn('work_id IS NULL AND work_locked = 0', sql)

    def test_the_download_archives_are_matched_on_the_whole_path(self):
        # Both archives store an absolute path -- SoundCloud in `filename`, YouTube in
        # `path`. Comparing a basename against SoundCloud's column matched none of its
        # 157.393 rows, so every rip read as "not from SoundCloud" and the 1.162 that
        # carry a label collected the bonus meant for an official release.
        cursor = ScriptedCursor([('AS batch', None, [])])
        worker.assign_works(cursor)
        sql = cursor.statements_matching('AS batch')[0][0]
        self.assertIn('sc.filename = mf.file_path', sql)
        self.assertIn('yt.path = mf.file_path', sql)
        self.assertNotIn('SUBSTRING_INDEX', sql)

    def test_a_set_is_not_grouped_with_another_set_of_the_same_name(self):
        # Two hour-long episodes of one show carry one title. Grouped, a canonical
        # filter would show one of them and hide the rest.
        long_file = {'file_path': '/mnt/music/Soundcloud/a.mp3', 'file_size': 80_000_000, 'duration_secs': 3600}
        rows = [
            _row(1, 'Andromedha Guest Mix', artist=None, files=long_file),
            _row(2, 'Andromedha Guest Mix', artist=None, files=long_file),
        ]
        cursor = ScriptedCursor(
            [
                ('AS batch', None, rows),
                ('SELECT id FROM library_works WHERE work_key', None, {'id': 41}),
            ]
        )
        worker.assign_works(cursor, limit=10)
        keys = {params[0] for _sql, params in cursor.statements_matching('INSERT INTO library_works')}
        self.assertEqual(len(keys), 2, keys)

    def test_the_batch_is_limited_before_the_files_are_joined(self):
        # LIMIT counts joined rows. Limiting the joined result cut the last track of
        # a batch off from its remaining files, and it left the pass with a work, so
        # it never came back: a track could be scored on its MP3 while its FLAC sat
        # one row beyond the limit.
        cursor = ScriptedCursor([('AS batch', None, [])])
        worker.assign_works(cursor)
        sql = cursor.statements_matching('AS batch')[0][0]
        self.assertLess(sql.index('LIMIT %s'), sql.index('library_media_files'))

    def test_two_title_less_tracks_do_not_become_one_song(self):
        # The defect this replaces: every title that normalizes away produced the
        # key ':::', and production collected 117 unrelated recordings that way.
        rows = [_row(1, '', artist=None), _row(2, '🕊', artist=None)]
        cursor = ScriptedCursor(
            [
                ('AS batch', None, rows),
                ('SELECT id FROM library_works WHERE work_key', None, {'id': 40}),
            ]
        )
        _touched, assigned = worker.assign_works(cursor, limit=10)

        self.assertEqual(assigned, 2)
        inserts = cursor.statements_matching('INSERT INTO library_works')
        keys = [params[0] for _sql, params in inserts]
        self.assertEqual(len(set(keys)), 2, keys)


class RecomputeCanonicalsTest(unittest.TestCase):
    def test_a_pin_wins_over_the_score(self):
        cursor = ScriptedCursor(
            [
                ('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': 2}),
                ('WHERE id = %s AND work_id = %s', (2, 40), {'id': 2}),
                ('ORDER BY t.version_score DESC', (40,), {'id': 1}),
            ]
        )
        self.assertEqual(worker.recompute_canonicals(cursor, {40}), 1)
        # The best-track query must not even run: a pin is a decision, and
        # asking the ranking anyway invites a later refactor to let it win.
        self.assertEqual(cursor.statements_matching('ORDER BY t.version_score'), [])
        updates = cursor.statements_matching('UPDATE library_works SET canonical_track_id')
        self.assertEqual([params for _sql, params in updates], [(2, 40)])

    def test_without_a_pin_the_best_score_wins(self):
        cursor = ScriptedCursor(
            [
                ('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': None}),
                ('ORDER BY t.version_score DESC', (40,), {'id': 1}),
            ]
        )
        worker.recompute_canonicals(cursor, {40})
        updates = cursor.statements_matching('UPDATE library_works SET canonical_track_id')
        self.assertEqual([params for _sql, params in updates], [(1, 40)])

    def test_a_work_with_no_tracks_gets_a_null_canonical(self):
        # Every track split out of a work leaves it empty; a stale canonical
        # there would point at a track that now belongs somewhere else.
        cursor = ScriptedCursor([('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': None})])
        worker.recompute_canonicals(cursor, {40})
        updates = cursor.statements_matching('UPDATE library_works SET canonical_track_id')
        self.assertEqual([params for _sql, params in updates], [(None, 40)])

    def test_a_pin_on_a_track_that_left_is_cleared(self):
        # Splitting a pinned track moves it to a work of its own and leaves the pin
        # behind. Following it made the old work canonical-point at a track that now
        # belongs to another song.
        cursor = ScriptedCursor(
            [
                ('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': 2}),
                ('WHERE id = %s AND work_id = %s', (2, 40), None),
                ('ORDER BY t.version_score DESC', (40,), {'id': 1}),
            ]
        )
        worker.recompute_canonicals(cursor, {40})

        cleared = cursor.statements_matching('UPDATE library_works SET pinned_track_id = NULL')
        self.assertEqual([params for _sql, params in cleared], [(40,)])
        updates = cursor.statements_matching('UPDATE library_works SET canonical_track_id')
        self.assertEqual([params for _sql, params in updates], [(1, 40)])

    def test_a_work_that_no_longer_exists_is_skipped(self):
        cursor = ScriptedCursor([])
        self.assertEqual(worker.recompute_canonicals(cursor, {999}), 1)
        self.assertEqual(cursor.statements_matching('UPDATE'), [])

    def test_the_tie_break_is_stable(self):
        # Equal scores must resolve the same way on every pass, or the canonical
        # wanders between two identical files. The ORDER BY is the whole rule.
        cursor = ScriptedCursor([('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': None})])
        worker.recompute_canonicals(cursor, {40})
        sql = cursor.statements_matching('ORDER BY t.version_score DESC')[0][0]
        self.assertIn('t.created_at ASC', sql)
        self.assertIn('t.id ASC', sql)


class GroupOnceTest(unittest.TestCase):
    def _conn(self, cursor):
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_a_moved_pin_is_recomputed_even_when_nothing_was_assigned(self):
        cursor = ScriptedCursor(
            [
                ('AS batch', None, []),
                ('pinned_track_id <> COALESCE(canonical_track_id, 0)', None, [{'id': 41}]),
                ('SELECT pinned_track_id FROM library_works', (41,), {'pinned_track_id': 9}),
                ('WHERE id = %s AND work_id = %s', (9, 41), {'id': 9}),
                ('SELECT COUNT(*) AS n FROM library_tracks', None, {'n': 0}),
            ]
        )
        conn = self._conn(cursor)
        stats = worker.group_once(conn)
        self.assertEqual(stats, {'assigned': 0, 'remaining': 0, 'recomputed': 1})
        updates = cursor.statements_matching('UPDATE library_works SET canonical_track_id')
        self.assertEqual([params for _sql, params in updates], [(9, 41)])
        conn.commit.assert_called_once()

    def test_a_quiet_pass_writes_nothing_and_reports_the_backlog(self):
        cursor = ScriptedCursor(
            [
                ('AS batch', None, []),
                ('pinned_track_id <> COALESCE(canonical_track_id, 0)', None, []),
                ('SELECT COUNT(*) AS n FROM library_tracks', None, {'n': 0}),
            ]
        )
        stats = worker.group_once(self._conn(cursor))
        self.assertEqual(stats, {'assigned': 0, 'remaining': 0, 'recomputed': 0})
        self.assertEqual(cursor.statements_matching('UPDATE'), [])

    def test_remaining_counts_what_the_batch_did_not_reach(self):
        cursor = ScriptedCursor(
            [
                ('AS batch', None, [_row(1, 'One')]),
                ('SELECT id FROM library_works WHERE work_key', None, {'id': 40}),
                ('pinned_track_id <> COALESCE(canonical_track_id, 0)', None, []),
                ('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': None}),
                ('ORDER BY t.version_score DESC', (40,), {'id': 1}),
                ('SELECT COUNT(*) AS n FROM library_tracks', None, {'n': 499}),
            ]
        )
        stats = worker.group_once(self._conn(cursor))
        self.assertEqual(stats, {'assigned': 1, 'remaining': 499, 'recomputed': 1})


if __name__ == '__main__':
    unittest.main()
