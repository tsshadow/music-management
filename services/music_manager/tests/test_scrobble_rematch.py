"""The SQL half of listen matching: the ladder of lookups and the retry queue.

The matching rules are pinned in test_scrobble_matching.py against pure
functions. This module is about what wraps them: that tiers are tried in ladder
order and the first hit ends the search, that fuzzy matching never leaves the
candidate set an exact key narrowed, that a listen which links is moved out of
the unmatched table and one which does not is scheduled further away each time,
and that a NULL normalized key -- the silent failure the design removed -- gets
filled before anything is retried.

tests/integration/test_scrobble_rematch.py runs the same code against MariaDB.
Here it runs against a ScriptedCursor, so the assertions are about statements
and control flow rather than about what the database makes of them.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.music_manager import scrobble_rematch as rematch
from services.music_manager.scrobble_matching import MatchTier, normalize
from services.music_manager.tests.scripted_cursor import (
    ScriptedCursor,
    transaction_log,
)

EXACT_SQL = 'WHERE a.name = %s AND t.title = %s'
NORMALIZED_SQL = 'WHERE a.normalized_name = %s AND t.normalized_title = %s'
BASE_TITLE_SQL = 'WHERE a.normalized_name = %s AND t.normalized_base_title = %s'
FUZZY_BY_ARTIST_SQL = 'WHERE a.normalized_name = %s LIMIT 200'
FUZZY_BY_TITLE_SQL = 'WHERE t.normalized_base_title = %s LIMIT 200'


def _all_tiers():
    return patch.object(rematch, 'tiers', return_value=list(MatchTier))


class BackfillNormalizedTest(unittest.TestCase):
    def test_fills_both_tables_and_counts_every_row(self):
        cursor = ScriptedCursor(
            [
                ('FROM library_artists WHERE normalized_name IS NULL', None, [{'id': 1, 'name': 'Angerfist'}]),
                (
                    'FROM library_tracks WHERE normalized_title IS NULL',
                    None,
                    [{'id': 5, 'title': 'Raise Your Fist (Radio Edit)'}],
                ),
            ]
        )
        self.assertEqual(rematch.backfill_normalized(cursor, limit=10), 2)

        artist_updates = cursor.statements_matching('UPDATE library_artists SET normalized_name')
        self.assertEqual([params for _sql, params in artist_updates], [(normalize('Angerfist'), 1)])

        track_updates = cursor.statements_matching('UPDATE library_tracks SET normalized_title')
        self.assertEqual(len(track_updates), 1)
        normalized_title, normalized_base, track_id = track_updates[0][1]
        self.assertEqual(track_id, 5)
        self.assertEqual(normalized_title, normalize('Raise Your Fist (Radio Edit)'))
        # The base title is the key the BASE_TITLE tier matches on: the version
        # suffix has to be gone from it or that tier never fires.
        self.assertEqual(normalized_base, normalize('Raise Your Fist'))

    def test_keys_are_cut_to_the_column_width(self):
        # normalized_* columns are VARCHAR(191); a longer key would make the
        # UPDATE fail on strict mode and silently truncate otherwise, and either
        # way the row would never match the same key computed at lookup time.
        cursor = ScriptedCursor(
            [('FROM library_artists WHERE normalized_name IS NULL', None, [{'id': 1, 'name': 'x' * 400}])]
        )
        rematch.backfill_normalized(cursor)
        stored = cursor.statements_matching('UPDATE library_artists SET normalized_name')[0][1][0]
        self.assertEqual(len(stored), 191)

    def test_nothing_missing_means_nothing_written(self):
        cursor = ScriptedCursor([])
        self.assertEqual(rematch.backfill_normalized(cursor), 0)
        self.assertEqual(cursor.statements_matching('UPDATE'), [])

    def test_the_limit_bounds_both_queries(self):
        cursor = ScriptedCursor([])
        rematch.backfill_normalized(cursor, limit=25)
        self.assertEqual(cursor.statements_matching('normalized_name IS NULL')[0][1], (25,))
        self.assertEqual(cursor.statements_matching('normalized_title IS NULL')[0][1], (25,))


class FindTrackLadderTest(unittest.TestCase):
    def test_an_exact_hit_ends_the_search(self):
        cursor = ScriptedCursor([(EXACT_SQL, ('Angerfist', 'Raise Your Fist'), {'id': 5})])
        with _all_tiers():
            found = rematch.find_track(cursor, 'Angerfist', 'Raise Your Fist')
        self.assertEqual(found, (5, MatchTier.EXACT, None))
        self.assertEqual(len(cursor.executed), 1)

    def test_a_miss_falls_through_to_the_next_tier(self):
        cursor = ScriptedCursor([(NORMALIZED_SQL, None, {'id': 6})])
        with _all_tiers():
            found = rematch.find_track(cursor, 'ANGERFIST', 'Raise Your Fist!')
        self.assertEqual(found, (6, MatchTier.NORMALIZED, None))
        self.assertEqual([sql for sql, _p in cursor.executed][0].count(EXACT_SQL), 1)
        # The normalized lookup is made with the normalized spelling, not the raw one.
        self.assertEqual(
            cursor.statements_matching(NORMALIZED_SQL)[0][1], (normalize('ANGERFIST'), normalize('Raise Your Fist!'))
        )

    def test_the_base_title_tier_strips_the_version(self):
        cursor = ScriptedCursor([(BASE_TITLE_SQL, None, {'id': 7})])
        with _all_tiers():
            found = rematch.find_track(cursor, 'Angerfist', 'Raise Your Fist (Radio Edit)')
        self.assertEqual(found, (7, MatchTier.BASE_TITLE, None))
        self.assertEqual(cursor.statements_matching(BASE_TITLE_SQL)[0][1][1], normalize('Raise Your Fist'))

    def test_no_tier_matching_is_none(self):
        cursor = ScriptedCursor([])
        with _all_tiers():
            self.assertIsNone(rematch.find_track(cursor, 'Nobody', 'Nothing'))

    def test_only_enabled_tiers_are_tried(self):
        # The ladder is configurable so a deployment can switch fuzzy off; a
        # disabled tier must not run even when it would have matched.
        cursor = ScriptedCursor([(NORMALIZED_SQL, None, {'id': 6})])
        with patch.object(rematch, 'tiers', return_value=[MatchTier.EXACT]):
            self.assertIsNone(rematch.find_track(cursor, 'Angerfist', 'Raise Your Fist'))
        self.assertEqual(cursor.statements_matching(NORMALIZED_SQL), [])


class FuzzyTierTest(unittest.TestCase):
    def test_candidates_are_narrowed_on_the_artist_first(self):
        cursor = ScriptedCursor(
            [
                (
                    FUZZY_BY_ARTIST_SQL,
                    None,
                    [
                        {'id': 1, 'normalized_title': normalize('Raise Your Fist')},
                        {'id': 2, 'normalized_title': normalize('Something Else Entirely')},
                    ],
                )
            ]
        )
        found = rematch._try_fuzzy(cursor, 'Angerfist', 'Raise Your Fists')
        self.assertIsNotNone(found)
        track_id, tier, score = found
        self.assertEqual((track_id, tier), (1, MatchTier.FUZZY))
        self.assertGreaterEqual(score, rematch.FUZZY_THRESHOLD)
        # The title-keyed fallback is only for an unknown artist; with candidates
        # in hand it must not run, or the artist narrowing was for nothing.
        self.assertEqual(cursor.statements_matching(FUZZY_BY_TITLE_SQL), [])

    def test_an_unknown_artist_falls_back_to_the_base_title_and_compares_artists(self):
        cursor = ScriptedCursor(
            [
                (FUZZY_BY_ARTIST_SQL, None, []),
                (FUZZY_BY_TITLE_SQL, None, [{'id': 3, 'normalized_name': normalize('Angerfist')}]),
            ]
        )
        # One stray letter in the artist: close enough to clear the threshold,
        # far enough that the exact artist key found nothing.
        found = rematch._try_fuzzy(cursor, 'Angerfists', 'Raise Your Fist (Radio Edit)')
        self.assertIsNotNone(found)
        self.assertEqual(found[0], 3)
        self.assertEqual(cursor.statements_matching(FUZZY_BY_TITLE_SQL)[0][1], (normalize('Raise Your Fist'),))

    def test_a_weak_best_candidate_is_not_a_match(self):
        # The threshold is the whole safety of this tier: below it, "closest of
        # a bad set" would link listens to music the library merely resembles.
        cursor = ScriptedCursor(
            [(FUZZY_BY_ARTIST_SQL, None, [{'id': 1, 'normalized_title': normalize('Completely Different Song')}])]
        )
        self.assertIsNone(rematch._try_fuzzy(cursor, 'Angerfist', 'Raise Your Fist'))

    def test_no_candidates_by_either_key_is_none(self):
        cursor = ScriptedCursor([])
        self.assertIsNone(rematch._try_fuzzy(cursor, 'Nobody', 'Nothing'))


class RecordMatchTest(unittest.TestCase):
    def test_writes_the_tier_and_keeps_an_earlier_played_secs(self):
        cursor = ScriptedCursor([])
        rematch.record_match(cursor, 5, '2026-08-01 10:00:00', 'user', 'lms', MatchTier.FUZZY, 93, None, None)
        sql, params = cursor.statements_matching('INSERT INTO scrobble_listens')[0]
        self.assertEqual(params, (5, '2026-08-01 10:00:00', 'user', 'lms', None, 'fuzzy', 93, None))
        # A rematch of a listen that already exists must not blank out a playing
        # time the first write recorded: COALESCE keeps the old value when the
        # new one is NULL.
        self.assertIn('played_secs = COALESCE(VALUES(played_secs), played_secs)', sql)
        self.assertIn('ON DUPLICATE KEY UPDATE match_method = VALUES(match_method)', sql)


class RetryCutoffTest(unittest.TestCase):
    def test_every_attempt_count_maps_to_a_growing_window(self):
        sql = rematch._retry_cutoff_sql()
        self.assertIn('last_attempt_at IS NULL', sql)
        for index, hours in enumerate(rematch.RETRY_HOURS):
            self.assertIn(f'WHEN attempts <= {index + 1} THEN {hours}', sql)
        # Past the table, the longest window applies forever rather than the
        # row being retried every cycle.
        self.assertIn(f'ELSE {rematch.RETRY_HOURS[-1]} END', sql)


class RematchOnceTest(unittest.TestCase):
    DUE = [
        {
            'id': 11,
            'artist_name': 'Angerfist',
            'track_title': 'Raise Your Fist',
            'listened_at': '2026-08-01 10:00:00',
            'username': 'user',
            'source': 'lms',
            'mbid_track': None,
            'played_secs': 210,
        },
        {
            'id': 12,
            'artist_name': 'Nobody',
            'track_title': 'Nothing',
            'listened_at': '2026-08-01 11:00:00',
            'username': 'user',
            'source': 'lms',
            'mbid_track': None,
            'played_secs': None,
        },
    ]

    def _conn(self, cursor):
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_a_linked_listen_moves_tables_and_a_miss_is_rescheduled(self):
        cursor = ScriptedCursor(
            [
                ('FROM scrobble_unmatched_listens WHERE', None, self.DUE),
                (EXACT_SQL, ('Angerfist', 'Raise Your Fist'), {'id': 5}),
            ]
        )
        conn = self._conn(cursor)
        with patch.object(rematch, 'tiers', return_value=[MatchTier.EXACT]):
            stats = rematch.rematch_once(conn, limit=50)

        self.assertEqual(stats, {'backfilled': 0, 'tried': 2, 'linked': 1})

        inserts = cursor.statements_matching('INSERT INTO scrobble_listens')
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][1], (5, '2026-08-01 10:00:00', 'user', 'lms', None, 'exact', None, 210))
        deletes = cursor.statements_matching('DELETE FROM scrobble_unmatched_listens')
        self.assertEqual([params for _sql, params in deletes], [(11,)])

        bumps = cursor.statements_matching('SET attempts = attempts + 1')
        self.assertEqual([params for _sql, params in bumps], [(12,)])

    def test_each_listen_is_committed_on_its_own(self):
        # One commit for the backfill and one per due row: a pass that dies
        # half-way keeps what it linked, and a row that fails does not roll
        # back the ones before it.
        cursor = ScriptedCursor([('FROM scrobble_unmatched_listens WHERE', None, self.DUE)])
        conn = self._conn(cursor)
        with patch.object(rematch, 'tiers', return_value=[MatchTier.EXACT]):
            rematch.rematch_once(conn)
        self.assertEqual(conn.commit.call_count, 1 + len(self.DUE))

    def test_the_backfill_runs_before_anything_is_retried(self):
        cursor = ScriptedCursor(
            [
                ('FROM library_tracks WHERE normalized_title IS NULL', None, [{'id': 5, 'title': 'Raise Your Fist'}]),
                ('FROM scrobble_unmatched_listens WHERE', None, []),
            ]
        )
        stats = rematch.rematch_once(self._conn(cursor))
        self.assertEqual(stats, {'backfilled': 1, 'tried': 0, 'linked': 0})
        order = [sql for sql, _p in cursor.executed]
        backfill_at = next(i for i, sql in enumerate(order) if 'normalized_title IS NULL' in sql)
        due_at = next(i for i, sql in enumerate(order) if 'FROM scrobble_unmatched_listens' in sql)
        self.assertLess(backfill_at, due_at)

    def test_due_rows_are_read_oldest_first_within_the_limit(self):
        cursor = ScriptedCursor([('FROM scrobble_unmatched_listens WHERE', None, [])])
        rematch.rematch_once(self._conn(cursor), limit=17)
        sql, params = cursor.statements_matching('FROM scrobble_unmatched_listens WHERE')[0]
        self.assertIn('ORDER BY listened_at ASC', sql)
        self.assertEqual(params, (17,))


class RematchAtomicityTest(unittest.TestCase):
    """A rematched listen is inserted and dequeued in one transaction per row."""

    DUE = RematchOnceTest.DUE
    _conn = RematchOnceTest._conn

    def rules(self):
        return [
            ('FROM scrobble_unmatched_listens WHERE', None, self.DUE[:1]),
            (EXACT_SQL, ('Angerfist', 'Raise Your Fist'), {'id': 5}),
        ]

    def test_the_insert_and_the_dequeue_are_one_transaction(self):
        cursor = ScriptedCursor(self.rules())
        conn = self._conn(cursor)
        log = transaction_log(conn, cursor)
        with patch.object(rematch, 'tiers', return_value=[MatchTier.EXACT]):
            rematch.rematch_once(conn, limit=50)
        row = log[log.index('BEGIN') :]
        insert = next(i for i, entry in enumerate(row) if 'INSERT INTO scrobble_listens' in entry)
        delete = next(i for i, entry in enumerate(row) if 'DELETE FROM scrobble_unmatched_listens' in entry)
        self.assertLess(insert, delete)
        self.assertLess(delete, row.index('COMMIT'))

    def test_a_failing_dequeue_rolls_the_listen_back(self):
        cursor = ScriptedCursor(self.rules())
        conn = self._conn(cursor)
        log = transaction_log(conn, cursor, fail_on='DELETE FROM scrobble_unmatched_listens')
        with patch.object(rematch, 'tiers', return_value=[MatchTier.EXACT]), self.assertRaises(RuntimeError):
            rematch.rematch_once(conn, limit=50)
        self.assertEqual(log.count('ROLLBACK'), 1)
        self.assertEqual(log[-1], 'ROLLBACK')


if __name__ == '__main__':
    unittest.main()
