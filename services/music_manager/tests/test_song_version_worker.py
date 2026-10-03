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

import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.music_manager import song_version_worker as worker
from services.music_manager.song_versions import ranking_signature, version_score
from services.music_manager.tests.scripted_cursor import (
    ScriptedCursor,
    assert_atomic,
    assert_rolled_back,
    transaction_log,
)

# Seconds and bytes chosen so the derived bitrate lands in different tiers: the
# FLAC is a lossless-sized file, the MP3 a 128k one.
FLAC = {'file_path': '/mnt/music/a.flac', 'file_size': 30_000_000, 'duration_secs': 300}
MP3 = {'file_path': '/mnt/music/a.mp3', 'file_size': 4_800_000, 'duration_secs': 300}


def _row(track_id, title, artist='Angerfist', files=MP3, has_label=1, from_soundcloud=0, from_youtube=0, form='track'):
    return {
        'id': track_id,
        'title': title,
        'form': form,
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
        self.assertEqual(score, version_score('extended', MP3['file_path'], 128, is_official=True))

    def test_a_labelled_track_from_soundcloud_is_not_official(self):
        # The label join alone would call a SoundCloud rip official whenever the
        # tagger managed to attach a label to it; the archive membership is what
        # says where the bytes came from.
        _kind, official = worker._rank_row(_row(1, 'Raise Your Fist'))
        _kind, ripped = worker._rank_row(_row(1, 'Raise Your Fist', from_soundcloud=1))
        self.assertGreater(official, ripped)

    def test_a_file_in_the_label_tree_is_official_without_a_label(self):
        context = worker.RankingContext(label_tree_roots=('/mnt/music/EPs',))
        todo = {'file_path': '/mnt/music/EPs/__TODO/x/a.mp3', 'file_size': 4_800_000, 'duration_secs': 300}
        _kind, queued = worker._rank_row(_row(1, 'Together', files=todo, has_label=0), context)
        _kind, loose = worker._rank_row(_row(1, 'Together', has_label=0), context)
        self.assertEqual(queued - loose, 1)

    def test_the_setting_reaches_the_score(self):
        lossless = worker._rank_row(_row(1, 'Raise Your Fist', files=FLAC), worker.RankingContext(True))[1]
        lossy = worker._rank_row(_row(1, 'Raise Your Fist', files=FLAC), worker.RankingContext(False))[1]
        self.assertGreater(lossless, lossy)

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
        # A new work carries the signature its tracks were just scored under; the upsert
        # never rewrites an existing work's signature, or the rescore would skip it.
        self.assertEqual(inserts[0][1][3], ranking_signature(True))
        self.assertNotIn('ranking_signature =', inserts[0][0])

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

    def test_only_a_track_with_a_file_can_become_canonical(self):
        # A retag leftover has no file and is older than its successor, so under a LEFT JOIN it
        # won the created_at tie-break and hid the real file in LMS (bug report 042).
        cursor = ScriptedCursor([('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': None})])
        worker.recompute_canonicals(cursor, {40})
        sql = cursor.statements_matching('ORDER BY t.version_score DESC')[0][0]
        self.assertIn('JOIN library_media_files mf ON mf.track_id = t.id', sql)
        self.assertNotIn('LEFT JOIN library_media_files', sql)


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


class NonMusicTest(unittest.TestCase):
    """An interview or a DVD preview is never a version of a song (docs/designs/non-music-forms/)."""

    def _conn(self, cursor):
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_two_interviews_of_one_name_get_a_work_each(self):
        cursor = ScriptedCursor(
            [
                (
                    'AS batch',
                    None,
                    [
                        _row(1, 'QAPITAL 2019 Interview', artist=None, form='interview'),
                        _row(2, 'QAPITAL 2019 Interview', artist=None, form='interview'),
                    ],
                ),
                ('SELECT id FROM library_works WHERE work_key', None, {'id': 40}),
            ]
        )
        worker.assign_works(cursor)
        keys = [params[0] for _sql, params in cursor.statements_matching('INSERT INTO library_works')]
        self.assertEqual(keys, ['track:1', 'track:2'])

    def test_a_grouped_interview_is_detached_and_its_old_work_recomputed(self):
        cursor = ScriptedCursor(
            [
                ('AND w.work_key <> CONCAT(%s, t.id)', None, [{'id': 7, 'work_id': 41}]),
                ('pinned_track_id <> COALESCE(canonical_track_id, 0)', None, []),
                ('SELECT pinned_track_id FROM library_works', (41,), {'pinned_track_id': None}),
                ('ORDER BY t.version_score DESC', (41,), {'id': 3}),
                ('SELECT COUNT(*) AS n FROM library_tracks', None, {'n': 1}),
            ]
        )
        stats = worker.group_once(self._conn(cursor))
        detach = cursor.statements_matching('AND w.work_key <> CONCAT(%s, t.id)')
        self.assertEqual(detach[0][1], ('interview', 'preview', 'track:'))
        updates = cursor.statements_matching('UPDATE library_tracks SET work_id = NULL')
        self.assertEqual([params for _sql, params in updates], [(7, 41)])
        canonical = cursor.statements_matching('UPDATE library_works SET canonical_track_id')
        self.assertEqual([params for _sql, params in canonical], [(3, 41)])
        self.assertEqual(stats['recomputed'], 1)

    def test_nothing_to_detach_writes_nothing(self):
        cursor = ScriptedCursor([])
        self.assertEqual(worker.detach_non_music(cursor), set())
        self.assertEqual(cursor.statements_matching('UPDATE'), [])


class GroupOnceAtomicityTest(unittest.TestCase):
    """One grouping batch is one transaction (bug report 115).

    The pool runs autocommit, so the commit the batch ended on committed nothing; a failure
    after the assignment and before the canonical left grouped works without one, and no
    later pass looks at a grouped track again.
    """

    RULES = [
        ('AS batch', None, [_row(1, 'One')]),
        ('SELECT id FROM library_works WHERE work_key', None, {'id': 40}),
        ('pinned_track_id <> COALESCE(canonical_track_id, 0)', None, []),
        ('SELECT pinned_track_id FROM library_works', (40,), {'pinned_track_id': None}),
        ('ORDER BY t.version_score DESC', (40,), {'id': 1}),
        ('SELECT COUNT(*) AS n FROM library_tracks', None, {'n': 0}),
    ]

    def _run(self, fail_on=None):
        cursor = ScriptedCursor(self.RULES)
        conn = MagicMock()
        conn.cursor.return_value = cursor
        log = transaction_log(conn, cursor, fail_on=fail_on)
        return conn, log

    def test_assignment_and_canonical_are_one_transaction(self):
        conn, log = self._run()
        self.assertEqual(worker.group_once(conn)['assigned'], 1)
        assert_atomic(
            self, log, 'INSERT INTO library_works', 'UPDATE library_tracks SET work_id', 'SET canonical_track_id'
        )

    def test_a_failing_canonical_update_rolls_the_assignment_back(self):
        conn, log = self._run(fail_on='SET canonical_track_id')
        with self.assertRaises(RuntimeError):
            worker.group_once(conn)
        assert_rolled_back(self, log)


class RankingContextTest(unittest.TestCase):
    def test_the_label_tree_and_the_queue_inside_it_are_one_root(self):
        settings = SimpleNamespace(prefer_lossless=True, eps_folder_path='/mnt/music/EPs', import_folder_path='')
        context = worker.ranking_context(settings)
        self.assertEqual(context.label_tree_roots, ('/mnt/music/EPs',))
        self.assertTrue(context.prefer_lossless)

    def test_a_queue_moved_out_of_the_tree_is_a_root_of_its_own(self):
        settings = SimpleNamespace(
            prefer_lossless=False, eps_folder_path='/mnt/music/EPs', import_folder_path='/mnt/music/Import'
        )
        context = worker.ranking_context(settings)
        self.assertEqual(context.label_tree_roots, ('/mnt/music/EPs', '/mnt/music/Import'))
        self.assertFalse(context.prefer_lossless)
        self.assertEqual(context.signature, ranking_signature(False))

    def test_nothing_configured_means_no_roots_and_lossless(self):
        context = worker.ranking_context(SimpleNamespace())
        self.assertEqual(context.label_tree_roots, ())
        self.assertTrue(context.prefer_lossless)


T0 = datetime.datetime(2026, 1, 1)
T1 = datetime.datetime(2026, 2, 1)


def _member(track_id, work_id, title, files=MP3, stored_kind=None, stored_score=None, created_at=T0, **flags):
    row = _row(track_id, title, files=files, **flags)
    row.update(work_id=work_id, version_kind=stored_kind, version_score=stored_score, created_at=created_at)
    return row


CONTEXT = worker.RankingContext(prefer_lossless=True, label_tree_roots=('/mnt/music/EPs',))
EPS_FLAC = {'file_path': '/mnt/music/EPs/Label/a.flac', 'file_size': 30_000_000, 'duration_secs': 300}
RIP = {'file_path': '/mnt/music/Soundcloud/a.mp3', 'file_size': 4_800_000, 'duration_secs': 300}


class BestTrackTest(unittest.TestCase):
    def test_only_a_member_with_a_file_can_win(self):
        rows = [
            _member(1, 40, 'A', files={'file_path': None, 'file_size': None, 'duration_secs': None}),
            _member(2, 40, 'A'),
        ]
        self.assertEqual(worker.best_track(rows, {1: 999, 2: 1}), 2)

    def test_ties_go_to_the_bigger_file_then_the_oldest_then_the_lowest_id(self):
        big = {'file_path': '/x/b.mp3', 'file_size': 9_000_000, 'duration_secs': 300}
        self.assertEqual(worker.best_track([_member(1, 40, 'A'), _member(2, 40, 'A', files=big)], {1: 5, 2: 5}), 2)
        self.assertEqual(
            worker.best_track([_member(1, 40, 'A', created_at=T1), _member(2, 40, 'A', created_at=T0)], {1: 5, 2: 5}),
            2,
        )
        self.assertEqual(worker.best_track([_member(2, 40, 'A'), _member(1, 40, 'A')], {1: 5, 2: 5}), 1)

    def test_no_member_with_a_file_is_no_canonical(self):
        self.assertIsNone(worker.best_track([], {}))

    def test_it_mirrors_the_sql_order(self):
        # The same decision in two places; if _BEST_TRACK's ORDER BY moves, this must too.
        for fragment in (
            't.version_score DESC',
            'mf.file_size / NULLIF(mf.duration_secs, 0)) DESC',
            't.created_at ASC',
            't.id ASC',
        ):
            self.assertIn(fragment, worker._BEST_TRACK)


class RescoreBatchTest(unittest.TestCase):
    """The rip used to win on the old ranking; the new one picks the release in EPs/."""

    def _cursor(self, members):
        return ScriptedCursor([('WHERE t.work_id BETWEEN', None, members)])

    def _members(self):
        return [
            _member(1, 40, 'Together', files=RIP, from_soundcloud=1, has_label=0, stored_kind='none', stored_score=7),
            _member(2, 40, 'Together', files=EPS_FLAC, has_label=0, stored_kind='none', stored_score=3),
        ]

    def test_a_changed_canonical_is_written_and_flagged(self):
        cursor = self._cursor(self._members())
        works = [{'id': 40, 'canonical_track_id': 1, 'pinned_track_id': None}]
        stats = worker.rescore_batch(cursor, works, CONTEXT)

        self.assertEqual(stats, {'works': 1, 'tracks_rescored': 2, 'canonicals_changed': 1})
        flagged = cursor.statements_matching('previous_canonical_track_id = %s')
        self.assertEqual([params for _sql, params in flagged], [(2, 1, 40)])
        self.assertIn('canonical_changed_at = CURRENT_TIMESTAMP', flagged[0][0])
        stamp = cursor.statements_matching('SET ranking_signature')
        self.assertEqual(stamp[0][1], (CONTEXT.signature, 40, 40, CONTEXT.signature))

    def test_it_never_regroups(self):
        cursor = self._cursor(self._members())
        worker.rescore_batch(cursor, [{'id': 40, 'canonical_track_id': 1, 'pinned_track_id': None}], CONTEXT)
        self.assertEqual(cursor.statements_matching('SET work_id'), [])
        self.assertEqual(cursor.statements_matching('INSERT'), [])

    def test_a_pin_wins_and_nothing_is_flagged(self):
        cursor = self._cursor(self._members())
        works = [{'id': 40, 'canonical_track_id': 1, 'pinned_track_id': 1}]
        stats = worker.rescore_batch(cursor, works, CONTEXT)
        self.assertEqual(stats['canonicals_changed'], 0)
        self.assertEqual(cursor.statements_matching('canonical_track_id = %s'), [])
        # The scores are still refreshed: the page shows them, pinned or not.
        self.assertEqual(len(cursor.statements_matching('UPDATE library_tracks SET version_kind')[0][1]), 2)

    def test_a_pin_on_a_track_that_left_is_cleared_and_the_ranking_decides(self):
        cursor = self._cursor(self._members())
        works = [{'id': 40, 'canonical_track_id': 9, 'pinned_track_id': 9}]
        worker.rescore_batch(cursor, works, CONTEXT)
        cleared = cursor.statements_matching('SET pinned_track_id = NULL')
        self.assertEqual([params for _sql, params in cleared], [(40,)])

    def test_a_work_without_a_canonical_gains_one_without_a_flag(self):
        cursor = self._cursor(self._members())
        stats = worker.rescore_batch(cursor, [{'id': 40, 'canonical_track_id': None, 'pinned_track_id': None}], CONTEXT)
        self.assertEqual(stats['canonicals_changed'], 0)
        plain = cursor.statements_matching('UPDATE library_works SET canonical_track_id = %s WHERE id = %s')
        self.assertEqual([params for _sql, params in plain], [(2, 40)])

    def test_a_work_whose_tracks_lost_their_files_loses_its_canonical_without_a_flag(self):
        # Bug report 100: 77k such works landed on the Versies page's "changed" list.
        no_file = {'file_path': None, 'file_size': None, 'duration_secs': None}
        cursor = self._cursor([_member(7, 40, 'Gone', files=no_file, stored_kind='none', stored_score=3)])
        stats = worker.rescore_batch(cursor, [{'id': 40, 'canonical_track_id': 7, 'pinned_track_id': None}], CONTEXT)
        self.assertEqual(stats['canonicals_changed'], 0)
        plain = cursor.statements_matching('UPDATE library_works SET canonical_track_id = %s WHERE id = %s')
        self.assertEqual([params for _sql, params in plain], [(None, 40)])
        self.assertEqual(cursor.statements_matching('previous_canonical_track_id = %s'), [])

    def test_a_second_run_over_rescored_data_writes_only_the_stamp(self):
        # Idempotence: feed the batch the scores and canonical the first run produced.
        first = self._members()
        best = worker._best_per_track(first, CONTEXT)
        for row in first:
            row['version_kind'] = best[row['id']]['kind']
            row['version_score'] = best[row['id']]['score']
        cursor = self._cursor(first)
        stats = worker.rescore_batch(cursor, [{'id': 40, 'canonical_track_id': 2, 'pinned_track_id': None}], CONTEXT)
        self.assertEqual(stats, {'works': 1, 'tracks_rescored': 0, 'canonicals_changed': 0})
        writes = [sql for sql, _params in cursor.executed if sql.startswith('UPDATE')]
        self.assertEqual(len(writes), 1)
        self.assertIn('SET ranking_signature', writes[0])

    def test_a_dry_run_counts_and_writes_nothing(self):
        cursor = self._cursor(self._members())
        stats = worker.rescore_batch(
            cursor, [{'id': 40, 'canonical_track_id': 1, 'pinned_track_id': None}], CONTEXT, dry_run=True
        )
        self.assertEqual(stats['canonicals_changed'], 1)
        self.assertEqual(cursor.statements_matching('UPDATE'), [])


class RescoreOnceTest(unittest.TestCase):
    def _conn(self, cursor):
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_it_walks_the_works_in_id_order_and_commits_per_batch(self):
        cursor = ScriptedCursor(
            [
                (
                    'AND id > %s',
                    (CONTEXT.signature, 0, 1),
                    [{'id': 40, 'canonical_track_id': None, 'pinned_track_id': None}],
                ),
                (
                    'AND id > %s',
                    (CONTEXT.signature, 40, 1),
                    [{'id': 41, 'canonical_track_id': None, 'pinned_track_id': None}],
                ),
                ('WHERE t.work_id BETWEEN', None, []),
            ]
        )
        conn = self._conn(cursor)
        stats = worker.rescore_once(conn, CONTEXT, batch_size=1)
        self.assertEqual(stats['works'], 2)
        self.assertEqual(conn.commit.call_count, 2)
        walked = [params for _sql, params in cursor.statements_matching('AND id > %s')]
        self.assertEqual(walked, [(CONTEXT.signature, 0, 1), (CONTEXT.signature, 40, 1), (CONTEXT.signature, 41, 1)])

    def test_a_dry_run_never_commits(self):
        cursor = ScriptedCursor(
            [
                (
                    'AND id > %s',
                    (CONTEXT.signature, 0, 500),
                    [{'id': 40, 'canonical_track_id': None, 'pinned_track_id': None}],
                ),
                ('WHERE t.work_id BETWEEN', None, []),
            ]
        )
        conn = self._conn(cursor)
        worker.rescore_once(conn, CONTEXT, dry_run=True)
        conn.commit.assert_not_called()

    def test_only_works_under_another_signature_are_selected(self):
        self.assertIn('ranking_signature IS NULL OR ranking_signature <> %s', worker._RESCORE_WORKS)


class RescoreTickTest(unittest.TestCase):
    def test_nothing_pending_does_nothing(self):
        conn = MagicMock()
        conn.cursor.return_value = ScriptedCursor([])
        with patch.object(worker, 'rescore_once') as rescore:
            self.assertIsNone(worker.rescore_tick(conn, CONTEXT))
        rescore.assert_not_called()

    def test_a_pending_ranking_is_measured_before_it_is_applied(self):
        conn = MagicMock()
        conn.cursor.return_value = ScriptedCursor([('SELECT 1 AS pending', None, {'pending': 1})])
        counts = {'works': 3, 'tracks_rescored': 2, 'canonicals_changed': 1}
        with (
            patch.object(worker, 'rescore_once', return_value=counts) as rescore,
            self.assertLogs('music-manager.song-versions', 'INFO') as logs,
        ):
            worker.rescore_tick(conn, CONTEXT)
        self.assertEqual([call.kwargs.get('dry_run', False) for call in rescore.call_args_list], [True, False])
        self.assertIn('change 1 canonicals', logs.output[0])


if __name__ == '__main__':
    unittest.main()


class DrainBacklogTest(unittest.TestCase):
    """Bug report 101: one 500-track batch an hour never caught up with a label-tree rescan."""

    def _drain(self, batches, budget=300, ticks=None):
        clock = iter(ticks or [0.0] * (len(batches) + 1))
        with patch.object(worker, 'group_once', side_effect=batches) as group_once:
            stats = worker.drain_backlog(MagicMock(), None, budget=budget, clock=lambda: next(clock))
        return stats, group_once.call_count

    def test_it_keeps_going_until_the_backlog_is_empty(self):
        batches = [
            {'assigned': 500, 'recomputed': 40, 'remaining': 700},
            {'assigned': 500, 'recomputed': 30, 'remaining': 200},
            {'assigned': 200, 'recomputed': 10, 'remaining': 0},
        ]
        stats, calls = self._drain(batches)
        self.assertEqual(calls, 3)
        self.assertEqual(stats, {'assigned': 1200, 'recomputed': 80, 'remaining': 0, 'batches': 3})

    def test_it_stops_when_the_budget_is_spent(self):
        batches = [{'assigned': 500, 'recomputed': 1, 'remaining': 10_000}] * 5
        stats, calls = self._drain(batches, budget=300, ticks=[0.0, 100.0, 250.0, 301.0])
        self.assertEqual(calls, 3)
        self.assertEqual(stats['remaining'], 10_000)

    def test_a_batch_that_assigns_nothing_ends_the_pass(self):
        # Tracks that cannot be grouped now must not make the pass spin until the budget ends.
        batches = [{'assigned': 0, 'recomputed': 0, 'remaining': 4}]
        stats, calls = self._drain(batches)
        self.assertEqual(calls, 1)
        self.assertEqual(stats['remaining'], 4)

    def test_the_tick_drains_instead_of_running_one_batch(self):
        conn = MagicMock()
        with (
            patch.object(worker, 'get_db_connection', return_value=conn),
            patch.object(worker, 'ranking_context', return_value=CONTEXT),
            patch.object(
                worker, 'drain_backlog', return_value={'assigned': 3, 'recomputed': 1, 'remaining': 0, 'batches': 1}
            ) as drain,
            patch.object(worker, 'rescore_tick') as rescore,
            patch.object(worker, 'group_once') as group_once,
        ):
            worker.grouping_tick()
        drain.assert_called_once_with(conn, CONTEXT)
        group_once.assert_not_called()
        rescore.assert_called_once_with(conn, CONTEXT)
        conn.close.assert_called_once()
