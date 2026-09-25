"""The LMS listen reconcile (bug report 039): the classifier, the loaders, the writes, the endpoints.

Everything here runs without a database: the classifier is pure, the loaders take a scripted
cursor or an in-memory SQLite standing in for `lms.db`. tests/integration/test_scrobble_reconcile.py
runs the same flow against a real MariaDB.
"""

import os
import random
import sqlite3
import time
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils', 'DatabaseConnector')


import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda only_sources=None: None  # type: ignore[assignment]

from fastapi.testclient import TestClient

from services.music_manager import scrobble_reconcile as rec
from services.music_manager.main import app
from services.music_manager.routers import reconcile as reconcile_router

API_KEY = users_router.API_KEY
T0 = 1_787_000_000  # an arbitrary moment in 2026


def muma(id_, at, track=1, user='user', created=None, source='lms'):
    """A muma listen; by default rewritten (created_at an hour before listened_at)."""
    return rec.MumaListen(id_, user, track, at, at - 3600 if created is None else created, source)


def lms(id_, at, track=1, user='user', server='server-a'):
    """An LMS listen already resolved to muma track `track`."""
    return rec.LmsListen(server, id_, user, track, at)


class ParseLmsDatetimeTest(unittest.TestCase):
    """LMS's `date_time` text is UTC, whatever zone this process runs in."""

    def test_wt_dbo_text_is_read_as_utc_and_floored(self):
        expected = int(datetime(2026, 8, 21, 19, 2, 5, tzinfo=UTC).timestamp())
        self.assertEqual(rec.parse_lms_datetime('2026-08-21T19:02:05.987'), expected)
        self.assertEqual(rec.parse_lms_datetime('2026-08-21 19:02:05'), expected)
        self.assertEqual(rec.parse_lms_datetime('2026-08-21T19:02:05Z'), expected)

    def test_an_explicit_offset_is_honoured(self):
        expected = int(datetime(2026, 8, 21, 19, 2, 5, tzinfo=UTC).timestamp())
        self.assertEqual(rec.parse_lms_datetime('2026-08-21T21:02:05+02:00'), expected)

    def test_a_number_is_already_unix_seconds(self):
        self.assertEqual(rec.parse_lms_datetime(1700000000.9), 1700000000)

    @unittest.skipUnless(hasattr(time, 'tzset'), 'needs time.tzset')
    def test_the_process_zone_never_enters(self):
        expected = int(datetime(2026, 3, 29, 1, 30, 0, tzinfo=UTC).timestamp())  # Amsterdam DST switch
        old = os.environ.get('TZ')
        os.environ['TZ'] = 'Europe/Amsterdam'
        time.tzset()
        try:
            self.assertEqual(rec.parse_lms_datetime('2026-03-29T01:30:00.000'), expected)
        finally:
            if old is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = old
            time.tzset()


class ClassifyTest(unittest.TestCase):
    """Every class, the five-second boundary, and the tie rules."""

    def test_five_seconds_apart_is_exact(self):
        result = rec.classify([muma(1, T0 + 5)], [lms(10, T0)])
        self.assertEqual([(m.id, listen.id) for m, listen in result.exact], [(1, 10)])
        self.assertEqual(result.shifted, [])

    def test_six_seconds_later_on_a_rewritten_row_is_shifted(self):
        result = rec.classify([muma(1, T0 + 6)], [lms(10, T0)])
        self.assertEqual([(m.id, listen.id) for m, listen in result.shifted], [(1, 10)])
        self.assertEqual(result.exact, [])
        self.assertEqual(result.lms_only, [])

    def test_the_exact_boundary_holds_in_both_directions(self):
        result = rec.classify([muma(1, T0 - 5)], [lms(10, T0)])
        self.assertEqual(len(result.exact), 1)

    def test_an_untouched_row_is_never_shifted(self):
        """created_at == listened_at: a second play, not a moved one."""
        result = rec.classify([muma(1, T0 + 600, created=T0 + 600)], [lms(10, T0)])
        self.assertEqual(result.shifted, [])
        self.assertEqual([m.id for m in result.muma_only], [1])
        # Its LMS listen is reported, but not insertable: an unclaimed muma listen of the
        # same track could be its counterpart.
        self.assertEqual([(listen.id, ok) for listen, ok in result.lms_only], [(10, False)])

    def test_a_muma_listen_earlier_than_lms_is_not_shifted(self):
        """The bug only ever moved a time forward, to NOW()."""
        result = rec.classify([muma(1, T0 - 600)], [lms(10, T0)])
        self.assertEqual(result.shifted, [])
        self.assertEqual([m.id for m in result.muma_only], [1])

    def test_an_imported_listen_is_never_shifted(self):
        result = rec.classify([muma(1, T0 + 600, source='listenbrainz')], [lms(10, T0)])
        self.assertEqual(result.shifted, [])
        self.assertEqual([m.id for m in result.muma_only], [1])

    def test_a_listen_lms_never_saw_is_muma_only(self):
        result = rec.classify([muma(1, T0, track=7)], [lms(10, T0, track=8)])
        self.assertEqual([m.id for m in result.muma_only], [1])
        self.assertEqual([(listen.id, ok) for listen, ok in result.lms_only], [(10, False)])

    def test_another_users_listen_does_not_pair(self):
        result = rec.classify([muma(1, T0, user='anna')], [lms(10, T0, user='user')])
        self.assertEqual(result.exact, [])
        self.assertEqual([m.id for m in result.muma_only], [1])

    def test_a_lost_listen_far_from_anything_is_insertable(self):
        result = rec.classify([muma(1, T0, track=2)], [lms(10, T0 + 3600, track=1)])
        self.assertEqual([(listen.id, ok) for listen, ok in result.lms_only], [(10, True)])

    def test_a_lost_listen_next_to_another_muma_listen_is_not_insertable(self):
        """The same play, matched to a different track: inserting it would count it twice."""
        result = rec.classify([muma(1, T0 + 2, track=2, created=T0 + 2)], [lms(10, T0, track=1)])
        self.assertEqual([(listen.id, ok) for listen, ok in result.lms_only], [(10, False)])

    def test_a_lost_listen_next_to_an_unmatched_listen_is_not_insertable(self):
        unmatched = {'user': [T0 + 9000, T0 + 1]}  # listened_at moved by bug 039, created_at intact
        result = rec.classify([], [lms(10, T0)], unmatched)
        self.assertEqual([(listen.id, ok) for listen, ok in result.lms_only], [(10, False)])

    def test_a_listen_next_to_a_muma_created_at_is_not_insertable(self):
        """A shifted row of another track still has its created_at at the moment of the play."""
        result = rec.classify([muma(1, T0 + 5000, track=2, created=T0 + 1)], [lms(10, T0, track=1)])
        self.assertEqual([(listen.id, ok) for listen, ok in result.lms_only], [(10, False)])

    def test_the_app_s_scrobble_of_another_track_a_minute_later_blocks_the_insert(self):
        """Bug 070: LMS records the start, the app scrobbles ~55 s later -- that is the same play."""
        result = rec.classify([muma(1, T0 + 55, track=2, created=T0 + 55, source='mobile')], [lms(10, T0, track=1)])
        self.assertEqual([(listen.id, ok) for listen, ok in result.lms_only], [(10, False)])

    def test_an_unmatched_listen_a_minute_later_blocks_the_insert(self):
        result = rec.classify([], [lms(10, T0)], {'user': [T0 + 55, T0 + 56]})
        self.assertEqual([(listen.id, ok) for listen, ok in result.lms_only], [(10, False)])

    def test_the_same_play_window_boundary(self):
        at_edge = rec.classify(
            [muma(1, T0 + rec.SAME_PLAY_WINDOW_SECONDS, track=2, created=T0 + rec.SAME_PLAY_WINDOW_SECONDS)],
            [lms(10, T0, track=1)],
        )
        self.assertEqual([ok for _, ok in at_edge.lms_only], [False])
        past_edge = rec.classify(
            [muma(1, T0 - rec.SAME_PLAY_WINDOW_SECONDS - 1, track=2, created=T0 - rec.SAME_PLAY_WINDOW_SECONDS - 1)],
            [lms(10, T0, track=1)],
        )
        self.assertEqual([ok for _, ok in past_edge.lms_only], [True])

    def test_a_listen_twenty_minutes_away_does_not_block_the_insert(self):
        result = rec.classify(
            [muma(1, T0 + 1200, track=2, created=T0 + 1200), muma(2, T0 - 1200, track=3, created=T0 - 1200)],
            [lms(10, T0, track=1)],
            {'user': [T0 + 1200, T0 - 1200]},
        )
        self.assertEqual([(listen.id, ok) for listen, ok in result.lms_only], [(10, True)])

    def test_the_wide_guard_does_not_change_exact_or_shifted_pairing(self):
        """Six seconds is still not exact, and a rewritten row a minute later is still shifted."""
        result = rec.classify([muma(1, T0 + 6, created=T0 + 6)], [lms(10, T0)])
        self.assertEqual(result.exact, [])
        self.assertEqual([m.id for m in result.muma_only], [1])
        result = rec.classify([muma(1, T0 + 60)], [lms(10, T0)])
        self.assertEqual([(m.id, listen.id) for m, listen in result.shifted], [(1, 10)])
        result = rec.classify([muma(1, T0 + 5, created=T0 + 5)], [lms(10, T0)])
        self.assertEqual([(m.id, listen.id) for m, listen in result.exact], [(1, 10)])

    def test_two_muma_listens_near_one_lms_listen_pair_the_closest(self):
        result = rec.classify([muma(1, T0 + 4), muma(2, T0 + 1)], [lms(10, T0)])
        self.assertEqual([(m.id, listen.id) for m, listen in result.exact], [(2, 10)])
        self.assertEqual([m.id for m in result.muma_only], [1])
        self.assertEqual(result.shifted, [])

    def test_two_shifted_rows_compete_for_one_lms_listen_the_nearest_wins(self):
        result = rec.classify([muma(1, T0 + 900), muma(2, T0 + 60)], [lms(10, T0)])
        self.assertEqual([(m.id, listen.id) for m, listen in result.shifted], [(2, 10)])
        self.assertEqual([m.id for m in result.muma_only], [1])

    def test_an_exact_pair_is_never_broken_to_serve_a_shifted_row(self):
        result = rec.classify([muma(1, T0 + 1), muma(2, T0 + 60)], [lms(10, T0)])
        self.assertEqual([(m.id, listen.id) for m, listen in result.exact], [(1, 10)])
        self.assertEqual(result.shifted, [])

    def test_each_shifted_row_takes_its_nearest_earlier_lms_listen(self):
        result = rec.classify(
            [muma(1, T0 + 5000), muma(2, T0 + 5100)],
            [lms(10, T0), lms(11, T0 + 4000)],
        )
        self.assertEqual(
            sorted((m.id, listen.id) for m, listen in result.shifted),
            [(1, 11), (2, 10)],
        )

    def test_an_unmapped_lms_listen_is_set_aside(self):
        unmapped = rec.LmsListen('server-a', 10, 'user', None, T0, '/music/gone.mp3')
        result = rec.classify([], [unmapped])
        self.assertEqual(result.lms_unmapped, [unmapped])
        self.assertEqual(result.lms_only, [])

    def test_the_result_does_not_depend_on_input_order(self):
        muma_rows = [muma(i, T0 + i * 7 + 30, track=i % 3) for i in range(1, 30)]
        lms_rows = [lms(100 + i, T0 + i * 11, track=i % 3) for i in range(1, 30)]
        expected = rec.classify(muma_rows, lms_rows).counts()
        pairs = sorted((m.id, listen.id) for m, listen in rec.classify(muma_rows, lms_rows).shifted)
        for seed in range(5):
            rng = random.Random(seed)
            shuffled_m, shuffled_l = muma_rows[:], lms_rows[:]
            rng.shuffle(shuffled_m)
            rng.shuffle(shuffled_l)
            again = rec.classify(shuffled_m, shuffled_l)
            self.assertEqual(again.counts(), expected)
            self.assertEqual(sorted((m.id, listen.id) for m, listen in again.shifted), pairs)

    def test_counts_and_sample(self):
        result = rec.classify(
            [muma(1, T0 + 1), muma(2, T0 + 600, track=2), muma(3, T0, track=3)],
            [lms(10, T0), lms(11, T0, track=2), lms(12, T0 + 99999, track=4)],
        )
        self.assertEqual(
            result.counts(),
            {
                'exact': 1,
                'shifted': 1,
                'muma_only': 1,
                'lms_only': 1,
                'lms_only_insertable': 1,
                'lms_unmapped': 0,
            },
        )
        shown = rec.sample(result, limit=5)
        self.assertEqual(shown['shifted'][0]['delta_seconds'], 600)
        self.assertTrue(shown['shifted'][0]['lms_listened_at'].endswith('Z'))
        self.assertEqual(shown['lms_only'][0]['insertable'], True)
        self.assertEqual(rec.sample(result, limit=0)['shifted'], [])


class UsernameCaseTest(unittest.TestCase):
    """`user` and `Teun` are one account on both sides (bug reports 070 and 074)."""

    def test_the_same_play_pairs_as_exact_across_spellings(self):
        result = rec.classify([muma(1, T0 + 1, user='user')], [lms(10, T0, user='Teun')])
        self.assertEqual([(m.id, listen.id) for m, listen in result.exact], [(1, 10)])
        self.assertEqual(result.lms_only, [])

    def test_the_same_play_guard_ignores_case(self):
        result = rec.classify(
            [muma(1, T0 + 55, track=2, user='user', created=T0 + 55)], [lms(10, T0, track=1, user='Teun')]
        )
        self.assertEqual([ok for _, ok in result.lms_only], [False])
        result = rec.classify([], [lms(10, T0, user='Teun')], {'user': [T0 + 55]})
        self.assertEqual([ok for _, ok in result.lms_only], [False])

    def test_canonicalize_uses_muma_s_users_spelling(self):
        muma_rows, lms_rows, unmatched = rec.canonicalize(
            {'user': 'user'},
            [muma(1, T0, user='Teun'), muma(2, T0, user='anna')],
            [lms(10, T0, user='Teun'), lms(11, T0, user='ANNA'), lms(12, T0, user='ghost')],
            {'Teun': [T0], 'user': [T0 + 1]},
        )
        self.assertEqual([m.username for m in muma_rows], ['user', 'anna'])
        self.assertEqual([listen.username for listen in lms_rows], ['user', 'anna', 'ghost'])
        self.assertEqual(unmatched, {'user': [T0, T0 + 1]})

    def test_load_canonical_usernames_keeps_the_oldest_account(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{'username': 'user'}, {'username': 'Teun'}, {'username': 'anna'}]
        self.assertEqual(rec.load_canonical_usernames(cursor), {'user': 'user', 'anna': 'anna'})
        self.assertIn('ORDER BY id', cursor.execute.call_args[0][0])

    def test_an_insert_carries_muma_s_spelling_and_an_unknown_user_is_never_insertable(self):
        lms_rows = [lms(10, T0, user='Teun'), lms(11, T0 + 99999, user='ghost')]
        with (
            patch.object(rec, 'load_lms_listens', return_value=lms_rows),
            patch.object(rec, 'load_muma_listens', return_value=[]),
            patch.object(rec, 'load_unmatched_times', return_value={}),
            patch.object(rec, 'load_canonical_usernames', return_value={'user': 'user'}),
        ):
            result = rec._analyse(MagicMock(), [], None)
        self.assertEqual([(listen.username, ok) for listen, ok in result.lms_only], [('ghost', False), ('user', True)])
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        rec._apply_user(conn, result, apply_shifted=False, insert_lms_only=True)
        inserted = [c.args[1] for c in cursor.execute.call_args_list if 'INSERT' in c.args[0]]
        self.assertEqual([params[2] for params in inserted], ['user'])

    def test_an_lms_username_filter_ignores_case(self):
        server = lms_db([('2026-08-21T19:02:05.000', 0, 1, 1, 1)], [(1, '/music/a/b.mp3')], users=(('Teun',),))
        rows = rec.read_lms_listens(server, 'server-a', 'user')
        self.assertEqual([row['username'] for row in rows], ['Teun'])


class FakeCursor:
    """A cursor answering `library_media_files` lookups from a dict of path -> track id."""

    def __init__(self, files):
        self.files = files
        self.rows = []
        self.queries = []

    def execute(self, sql, params=()):
        """Record the call; answer an `IN (...)` path lookup."""
        self.queries.append((sql, params))
        self.rows = [{'file_path': p, 'track_id': self.files[p]} for p in params if p in self.files]

    def fetchall(self):
        """The rows of the last lookup."""
        return self.rows


def lms_db(listens, tracks, users=(('user',),)):
    """An in-memory SQLite with LMS's `user`, `track` and `listen` columns this module reads."""
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE user (id INTEGER PRIMARY KEY, login_name TEXT)')
    conn.execute('CREATE TABLE track (id INTEGER PRIMARY KEY, absolute_file_path TEXT)')
    conn.execute(
        'CREATE TABLE listen (id INTEGER PRIMARY KEY, date_time TEXT, backend INTEGER, '
        'sync_state INTEGER, user_id INTEGER, track_id INTEGER)'
    )
    conn.executemany('INSERT INTO user (login_name) VALUES (?)', users)
    conn.executemany('INSERT INTO track (id, absolute_file_path) VALUES (?, ?)', tracks)
    conn.executemany(
        'INSERT INTO listen (date_time, backend, sync_state, user_id, track_id) VALUES (?, ?, ?, ?, ?)', listens
    )
    return conn


class LoadLmsListensTest(unittest.TestCase):
    """LMS listen -> track path -> muma track, across the /music vs /mnt/music spellings."""

    def test_an_lms_path_resolves_under_muma_s_mount(self):
        server = lms_db([('2026-08-21T19:02:05.000', 0, 1, 1, 1)], [(1, '/music/a/b.mp3')])
        loaded = rec.load_lms_listens(FakeCursor({'/mnt/music/a/b.mp3': 42}), [(server, 'server-a')], None)
        self.assertEqual([(listen.track_id, listen.username) for listen in loaded], [(42, 'user')])

    def test_listenbrainz_backend_and_pending_removal_are_skipped(self):
        server = lms_db(
            [
                ('2026-08-21T19:02:05.000', 1, 1, 1, 1),  # ListenBrainz backend
                ('2026-08-21T19:03:05.000', 0, 2, 1, 1),  # PendingRemove
                ('2026-08-21T19:04:05.000', 0, 0, 1, 1),  # PendingAdd still counts
            ],
            [(1, '/music/a.mp3')],
        )
        loaded = rec.load_lms_listens(FakeCursor({'/mnt/music/a.mp3': 1}), [(server, 'server-a')], None)
        self.assertEqual(len(loaded), 1)

    def test_the_same_play_on_two_servers_is_counted_once(self):
        row = [('2026-08-21T19:02:05.000', 0, 1, 1, 1)]
        first = lms_db(row, [(1, '/music/a.mp3')])
        second = lms_db(row, [(1, '/music/a.mp3')])
        loaded = rec.load_lms_listens(
            FakeCursor({'/mnt/music/a.mp3': 1}), [(first, 'server-a'), (second, 'server-b')], None
        )
        self.assertEqual([listen.server for listen in loaded], ['server-a'])

    def test_a_username_filter_reaches_lms(self):
        server = lms_db(
            [('2026-08-21T19:02:05.000', 0, 1, 1, 1), ('2026-08-21T19:02:05.000', 0, 1, 2, 1)],
            [(1, '/music/a.mp3')],
            users=(('user',), ('anna',)),
        )
        loaded = rec.load_lms_listens(FakeCursor({'/mnt/music/a.mp3': 1}), [(server, 'server-a')], 'anna')
        self.assertEqual([listen.username for listen in loaded], ['anna'])

    def test_an_unknown_file_is_unmapped(self):
        server = lms_db([('2026-08-21T19:02:05.000', 0, 1, 1, 1)], [(1, '/music/gone.mp3')])
        loaded = rec.load_lms_listens(FakeCursor({}), [(server, 'server-a')], None)
        self.assertEqual([(listen.track_id, listen.path) for listen in loaded], [(None, '/music/gone.mp3')])


def scripted_conn(offset_seconds=0, zone='SYSTEM'):
    """A connection whose cursor answers the zone probes and records everything else."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = lambda: {'offset_seconds': offset_seconds, 'zone': zone}
    return conn, cursor


class ZoneCheckTest(unittest.TestCase):
    """The relay's naive datetimes are only comparable when both sides share a zone."""

    def test_a_matching_offset_is_consistent(self):
        process = int(datetime.now().astimezone().utcoffset().total_seconds())
        conn, _ = scripted_conn(process + 1)
        self.assertTrue(rec.zone_check(conn)['consistent'])

    def test_a_different_offset_is_not(self):
        process = int(datetime.now().astimezone().utcoffset().total_seconds())
        conn, _ = scripted_conn(process + 7200)
        self.assertFalse(rec.zone_check(conn)['consistent'])

    def test_apply_refuses_before_writing_on_a_mismatch(self):
        process = int(datetime.now().astimezone().utcoffset().total_seconds())
        conn, cursor = scripted_conn(process + 3600)
        with self.assertRaises(rec.ZoneMismatchError):
            rec.apply(conn, [], None, True, True)
        conn.begin.assert_not_called()
        self.assertFalse(any('UPDATE' in str(c) for c in cursor.execute.call_args_list))


class DuplicateEntry(Exception):
    """Stands in for pymysql's IntegrityError, which the unit suite has stubbed out."""


class ApplyUserTest(unittest.TestCase):
    """One user's writes: one transaction, collisions counted, stale rows left alone."""

    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor

    def test_a_shifted_row_gets_lms_s_time_guarded_by_its_old_one(self):
        part = rec.Classification(shifted=[(muma(1, T0 + 600), lms(10, T0))])
        self.cursor.execute.return_value = 1
        totals = rec._apply_user(self.conn, part, apply_shifted=True, insert_lms_only=False)
        self.assertEqual(totals['shifted_fixed'], 1)
        sql, params = self.cursor.execute.call_args.args
        self.assertIn('WHERE id = %s AND listened_at = FROM_UNIXTIME(%s)', sql)
        self.assertEqual(params, (T0, 1, T0 + 600))
        self.conn.begin.assert_called_once()
        self.conn.commit.assert_called_once()

    def test_a_row_changed_since_the_read_is_counted_not_fixed(self):
        part = rec.Classification(shifted=[(muma(1, T0 + 600), lms(10, T0))])
        self.cursor.execute.return_value = 0
        totals = rec._apply_user(self.conn, part, apply_shifted=True, insert_lms_only=False)
        self.assertEqual((totals['shifted_fixed'], totals['changed_since_read']), (0, 1))

    def test_a_unique_collision_is_skipped_and_counted(self):
        part = rec.Classification(
            shifted=[(muma(1, T0 + 600), lms(10, T0))],
            lms_only=[(lms(11, T0 + 9999, track=2), True), (lms(12, T0 + 99999, track=3), False)],
        )
        self.cursor.execute.side_effect = [DuplicateEntry(1062, 'Duplicate entry'), 1]
        totals = rec._apply_user(self.conn, part, apply_shifted=True, insert_lms_only=True)
        self.assertEqual(totals, {'shifted_fixed': 0, 'lms_only_inserted': 1, 'collisions': 1, 'changed_since_read': 0})
        insert_sql, insert_params = self.cursor.execute.call_args.args
        self.assertIn('INSERT INTO scrobble_listens', insert_sql)
        self.assertEqual(insert_params, (2, T0 + 9999, 'user', 'lms-reconcile'))
        self.conn.commit.assert_called_once()

    def test_any_other_error_rolls_the_user_back(self):
        part = rec.Classification(shifted=[(muma(1, T0 + 600), lms(10, T0))])
        self.cursor.execute.side_effect = DuplicateEntry(1205, 'Lock wait timeout')
        with self.assertRaises(DuplicateEntry):
            rec._apply_user(self.conn, part, apply_shifted=True, insert_lms_only=False)
        self.conn.rollback.assert_called_once()
        self.conn.commit.assert_not_called()

    def test_nothing_is_written_for_a_repair_not_asked_for(self):
        part = rec.Classification(
            shifted=[(muma(1, T0 + 600), lms(10, T0))], lms_only=[(lms(11, T0 + 9999, track=2), True)]
        )
        totals = rec._apply_user(self.conn, part, apply_shifted=False, insert_lms_only=False)
        self.assertEqual(sum(totals.values()), 0)
        self.cursor.execute.assert_not_called()


class ReconcileEndpointTest(unittest.TestCase):
    """Admin only; the dry run answers inline, the apply runs in the background."""

    def setUp(self):
        self.client = TestClient(app)
        reconcile_router.reconcile_state.update({'running': False, 'last': None, 'error': None})
        self.addCleanup(reconcile_router.reconcile_state.update, {'running': False, 'last': None, 'error': None})

    def test_without_a_key_it_is_unauthorized(self):
        self.assertEqual(self.client.get('/api/scrobble/reconcile/lms').status_code, 401)

    def test_a_user_without_the_admin_role_is_refused(self):
        user = {'type': 'user', 'user': {'id': 4, 'username': 'anna', 'role_name': 'user', 'permissions': []}}
        headers = {'x-api-key': 'anna-key'}
        with (
            patch.object(users_router, 'verify_api_key', return_value=user),
            patch.object(reconcile_router, 'run_reconcile_apply') as run,
            patch.object(rec, 'dry_run') as dry,
        ):
            responses = [
                self.client.get('/api/scrobble/reconcile/lms', headers=headers),
                self.client.post('/api/scrobble/reconcile/lms', headers=headers, json={'apply_shifted': True}),
                self.client.get('/api/scrobble/reconcile/lms/status', headers=headers),
            ]
        self.assertEqual([r.status_code for r in responses], [403, 403, 403])
        run.assert_not_called()
        dry.assert_not_called()

    def test_an_admin_gets_the_dry_run(self):
        server = MagicMock()
        with (
            patch.object(reconcile_router, '_servers', return_value=[(server, 'server-a')]),
            patch.object(reconcile_router, 'get_db_connection', return_value=MagicMock()),
            patch.object(rec, 'dry_run', return_value={'totals': {'shifted': 3}}) as dry,
        ):
            response = self.client.get('/api/scrobble/reconcile/lms?username=user', headers={'x-api-key': API_KEY})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'totals': {'shifted': 3}})
        self.assertEqual(dry.call_args.args[2], 'user')
        server.close.assert_called_once()

    def test_no_visible_lms_database_is_a_503(self):
        with patch.object(users_router, 'lms_db_targets', return_value=[]):
            response = self.client.get('/api/scrobble/reconcile/lms', headers={'x-api-key': API_KEY})
        self.assertEqual(response.status_code, 503)

    def test_an_apply_with_nothing_to_do_is_refused(self):
        response = self.client.post('/api/scrobble/reconcile/lms', headers={'x-api-key': API_KEY}, json={})
        self.assertEqual(response.status_code, 400)

    def test_an_admin_starts_the_apply_in_the_background(self):
        with patch.object(reconcile_router, 'run_reconcile_apply') as run:
            response = self.client.post(
                '/api/scrobble/reconcile/lms',
                headers={'x-api-key': API_KEY},
                json={'username': 'user', 'apply_shifted': True},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = run.call_args.args[0]
        self.assertEqual((body.username, body.apply_shifted, body.insert_lms_only), ('user', True, False))

    def test_a_second_apply_is_refused_while_one_runs(self):
        reconcile_router.reconcile_state['running'] = True
        with patch.object(reconcile_router, 'run_reconcile_apply') as run:
            response = self.client.post(
                '/api/scrobble/reconcile/lms', headers={'x-api-key': API_KEY}, json={'apply_shifted': True}
            )
        self.assertEqual(response.status_code, 409)
        run.assert_not_called()

    def test_the_apply_records_its_totals_as_an_info_event(self):
        result = {'written': {'shifted_fixed': 2, 'lms_only_inserted': 0, 'collisions': 1, 'changed_since_read': 0}}
        reconcile_router.reconcile_state['running'] = True
        with (
            patch.object(reconcile_router, '_servers', return_value=[]),
            patch.object(reconcile_router, 'get_db_connection', return_value=MagicMock()),
            patch.object(rec, 'apply', return_value=result),
            patch('services.common.Helpers.EventService.event_service') as events,
        ):
            reconcile_router.run_reconcile_apply(reconcile_router.ReconcileRequest(apply_shifted=True))
        self.assertEqual(reconcile_router.reconcile_state, {'running': False, 'last': result, 'error': None})
        kwargs = events.emit.call_args.kwargs
        self.assertEqual(kwargs['level'], 'INFO')
        self.assertIn('2 shifted listens restored', kwargs['message'])

    def test_a_failed_apply_reports_its_error(self):
        reconcile_router.reconcile_state['running'] = True
        with (
            patch.object(reconcile_router, '_servers', return_value=[]),
            patch.object(reconcile_router, 'get_db_connection', return_value=MagicMock()),
            patch.object(rec, 'apply', side_effect=rec.ZoneMismatchError('offsets differ')),
        ):
            reconcile_router.run_reconcile_apply(reconcile_router.ReconcileRequest(apply_shifted=True))
        state = self.client.get('/api/scrobble/reconcile/lms/status', headers={'x-api-key': API_KEY}).json()
        self.assertEqual(state, {'running': False, 'last': None, 'error': 'offsets differ'})


if __name__ == '__main__':
    unittest.main()


class OpenServersTest(unittest.TestCase):
    """open_servers opens every target it is given, once per file.

    Dropping databases without the LMS schema happens earlier, in `lms_db_targets()`; see
    test_lms_schema.py.
    """

    def _db(self, directory, name, tables):
        """Create an on-disk SQLite file with the given empty tables."""
        import os

        path = os.path.join(directory, name)
        conn = sqlite3.connect(path)
        for table in tables:
            conn.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
        conn.commit()
        conn.close()
        return path

    def test_every_complete_database_is_kept(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            a = self._db(tmp, 'a.db', ['listen', 'user', 'track'])
            b = self._db(tmp, 'b.db', ['listen', 'user', 'track', 'extra'])
            servers = rec.open_servers([(a, 'a'), (b, 'b')])
            try:
                self.assertEqual([name for _, name in servers], ['a', 'b'])
            finally:
                for conn, _ in servers:
                    conn.close()
