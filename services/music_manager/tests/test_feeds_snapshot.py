"""The feeds snapshot (docs/designs/feeds/home-load.md, step 3): freshness per slug,
one build per key at a time, and the background pass that keeps it warm.

Runs against an in-memory `feeds_snapshot` table rather than a scripted cursor:
the questions here are about what a second read sees after a first write, which a
rule table cannot answer.
"""

import json
import threading
import unittest
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from services.music_manager.feeds import clock, snapshot

NOW = datetime(2026, 9, 18, 9, 30, 0)
KEY = 'settings-a'


class _Table:
    """`feeds_snapshot` and `scrobble_listens` as dicts, behind a cursor that
    understands exactly the statements snapshot.py issues."""

    def __init__(self, listeners=()):
        self.rows = {}
        self.listeners = list(listeners)
        self.executed = []
        self.commits = 0

    def connection(self):
        table = self

        class Cursor:
            rowcount = 0
            _result = None

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def execute(self, sql, params=None):
                statement = ' '.join(sql.split())
                table.executed.append((statement, params))
                self._result = None
                if statement.startswith('SELECT generated_at'):
                    self._result = table.rows.get(tuple(params))
                elif statement.startswith('INSERT INTO feeds_snapshot'):
                    username, slug, feed_date, generated_at, params_key, payload = params
                    table.rows[(username, slug, feed_date)] = {
                        'generated_at': generated_at,
                        'params_key': params_key,
                        'payload': payload,
                    }
                elif statement.startswith('DELETE FROM feeds_snapshot WHERE username'):
                    table.rows = {key: row for key, row in table.rows.items() if key[0] != params[0]}
                elif statement.startswith('DELETE FROM feeds_snapshot WHERE feed_date'):
                    doomed = [key for key in table.rows if key[2] < params[0]]
                    for key in doomed:
                        del table.rows[key]
                    self.rowcount = len(doomed)
                elif statement.startswith('SELECT DISTINCT username'):
                    self._result = [{'username': name} for name in table.listeners]

            def fetchone(self):
                return self._result

            def fetchall(self):
                return self._result or []

        class Connection:
            def cursor(self):
                return Cursor()

            def commit(self):
                table.commits += 1

            def close(self):
                pass

        return Connection()


def _payload(tag):
    return {'slug': 'x', 'tracks': [{'id': tag}]}


def _empty(tag):
    """A payload the way `feed_body` stores a mix that came out empty."""
    return {'slug': 'x', 'state': 'not_enough_data', 'tracks': [], 'tag': tag}


def _key(_conn, _username, _slug):
    """`params_key` for a refresh pass whose key never changes."""
    return KEY


class FreshnessTest(unittest.TestCase):
    def test_a_daily_mix_row_is_fresh_all_day(self):
        early = NOW.replace(hour=0, minute=1)
        self.assertTrue(snapshot.is_fresh('daily-mix-mid', early, KEY, KEY, NOW.replace(hour=23, minute=59)))

    def test_the_listing_row_is_fresh_all_day(self):
        self.assertTrue(snapshot.is_fresh(snapshot.LIST_SLUG, NOW - timedelta(hours=20), KEY, KEY, NOW))

    def test_the_radar_ages_out_after_its_ttl(self):
        just_inside = NOW - timedelta(seconds=snapshot.RADAR_TTL_SECONDS - 1)
        just_outside = NOW - timedelta(seconds=snapshot.RADAR_TTL_SECONDS + 1)
        self.assertTrue(snapshot.is_fresh('release-radar', just_inside, KEY, KEY, NOW))
        self.assertFalse(snapshot.is_fresh('release-radar', just_outside, KEY, KEY, NOW))

    def test_a_settings_change_ages_every_row_at_once(self):
        """An admin who moves the hardness edges sees them on the next read, not tomorrow."""
        self.assertFalse(snapshot.is_fresh('daily-mix-mid', NOW, 'settings-b', KEY, NOW))

    def test_an_empty_mix_ages_out_after_the_short_ttl(self):
        """Bug 049: a not_enough_data mix used to be fresh all day, so a listener who
        opened Home before their first listen saw empty mixes until tomorrow."""
        just_inside = NOW - timedelta(seconds=snapshot.NON_OK_TTL_SECONDS - 1)
        just_outside = NOW - timedelta(seconds=snapshot.NON_OK_TTL_SECONDS + 1)
        for state in ('not_enough_data', 'no_matches'):
            with self.subTest(state=state):
                self.assertTrue(snapshot.is_fresh('daily-mix-mid', just_inside, KEY, KEY, NOW, state))
                self.assertFalse(snapshot.is_fresh('daily-mix-mid', just_outside, KEY, KEY, NOW, state))

    def test_an_ok_mix_is_still_fresh_all_day(self):
        self.assertTrue(snapshot.is_fresh('daily-mix-mid', NOW - timedelta(hours=9), KEY, KEY, NOW, 'ok'))

    def test_an_empty_radar_ages_on_the_shorter_of_the_two_ttls(self):
        age = timedelta(seconds=snapshot.NON_OK_TTL_SECONDS + 1)
        self.assertLess(snapshot.NON_OK_TTL_SECONDS, snapshot.RADAR_TTL_SECONDS)
        self.assertFalse(snapshot.is_fresh('release-radar', NOW - age, KEY, KEY, NOW, 'no_matches'))


class FeedDateTest(unittest.TestCase):
    """The feed day is the configured zone's calendar day, not the container's UTC one."""

    def test_the_default_zone_rolls_over_at_amsterdam_midnight(self):
        with patch.dict('os.environ', {clock.TIMEZONE_ENV: ''}):
            # 22:30 UTC in September is 00:30 the next day in Amsterdam (CEST, UTC+2).
            self.assertEqual(clock.feed_date(datetime(2026, 9, 24, 22, 30, tzinfo=UTC)), date(2026, 9, 25))
            self.assertEqual(clock.feed_date(datetime(2026, 9, 24, 21, 59, tzinfo=UTC)), date(2026, 9, 24))
            # Winter time: UTC+1, so 23:30 UTC is already tomorrow and 22:59 is not.
            self.assertEqual(clock.feed_date(datetime(2026, 1, 10, 23, 30, tzinfo=UTC)), date(2026, 1, 11))
            self.assertEqual(clock.feed_date(datetime(2026, 1, 10, 22, 59, tzinfo=UTC)), date(2026, 1, 10))

    def test_the_zone_is_configurable(self):
        with patch.dict('os.environ', {clock.TIMEZONE_ENV: 'UTC'}):
            self.assertEqual(clock.feed_date(datetime(2026, 9, 24, 22, 30, tzinfo=UTC)), date(2026, 9, 24))

    def test_an_unknown_zone_falls_back_to_the_system_date_instead_of_failing(self):
        moment = datetime(2026, 9, 24, 22, 30, tzinfo=UTC)
        with patch.dict('os.environ', {clock.TIMEZONE_ENV: 'Nowhere/Atlantis'}):
            with self.assertLogs(clock.logger, level='WARNING'):
                clock._zone.cache_clear()
                self.assertEqual(clock.feed_date(moment), moment.date())

    def test_a_request_after_local_midnight_is_a_new_row(self):
        """Serve at 23:30 and at 00:30 Amsterdam time -- both 21:30/22:30 UTC on the
        same UTC day -- and the second must be tomorrow's mix, not today's row."""
        snapshot._locks.clear()
        table = _Table()
        conn = table.connection()
        before = datetime(2026, 9, 24, 21, 30, tzinfo=UTC)
        after = datetime(2026, 9, 24, 22, 30, tzinfo=UTC)
        with patch.dict('os.environ', {clock.TIMEZONE_ENV: 'Europe/Amsterdam'}):
            snapshot.serve(conn, 'user', 'daily-mix-mid', before, KEY, lambda: _payload('thursday'))
            payload, source = snapshot.serve(conn, 'user', 'daily-mix-mid', after, KEY, lambda: _payload('friday'))
        self.assertEqual((source, payload), ('live', _payload('friday')))
        self.assertEqual(
            sorted(key[2] for key in table.rows),
            [date(2026, 9, 24), date(2026, 9, 25)],
        )


class ServeTest(unittest.TestCase):
    def setUp(self):
        snapshot._locks.clear()
        self.table = _Table()
        self.conn = self.table.connection()

    def test_a_miss_builds_writes_and_reports_live(self):
        payload, source = snapshot.serve(self.conn, 'user', 'daily-mix-mid', NOW, KEY, lambda: _payload('built'))
        self.assertEqual(source, 'live')
        self.assertEqual(payload, _payload('built'))
        stored = self.table.rows[('user', 'daily-mix-mid', NOW.date())]
        self.assertEqual(json.loads(stored['payload']), _payload('built'))
        self.assertEqual(stored['params_key'], KEY)
        self.assertEqual(self.table.commits, 1)

    def test_a_second_read_is_the_row_and_costs_no_build(self):
        snapshot.serve(self.conn, 'user', 'daily-mix-mid', NOW, KEY, lambda: _payload('built'))
        builds = []
        payload, source = snapshot.serve(
            self.conn, 'user', 'daily-mix-mid', NOW + timedelta(hours=5), KEY, lambda: builds.append(1)
        )
        self.assertEqual(source, 'snapshot')
        self.assertEqual(payload, _payload('built'))
        self.assertEqual(builds, [])

    def test_tomorrow_is_a_different_row(self):
        snapshot.serve(self.conn, 'user', 'daily-mix-mid', NOW, KEY, lambda: _payload('today'))
        payload, source = snapshot.serve(
            self.conn, 'user', 'daily-mix-mid', NOW + timedelta(days=1), KEY, lambda: _payload('tomorrow')
        )
        self.assertEqual((source, payload), ('live', _payload('tomorrow')))

    def test_a_stale_radar_is_rebuilt_in_place(self):
        snapshot.serve(self.conn, 'user', 'release-radar', NOW, KEY, lambda: _payload('old'))
        later = NOW + timedelta(seconds=snapshot.RADAR_TTL_SECONDS + 5)
        payload, source = snapshot.serve(self.conn, 'user', 'release-radar', later, KEY, lambda: _payload('new'))
        self.assertEqual((source, payload), ('live', _payload('new')))
        self.assertEqual(len(self.table.rows), 1)

    def test_an_empty_mix_is_rebuilt_on_read_once_its_ttl_is_over(self):
        snapshot.serve(self.conn, 'user', 'daily-mix-mid', NOW, KEY, lambda: _empty('before-first-listen'))
        soon = NOW + timedelta(seconds=snapshot.NON_OK_TTL_SECONDS - 60)
        payload, source = snapshot.serve(self.conn, 'user', 'daily-mix-mid', soon, KEY, lambda: self.fail('fresh'))
        self.assertEqual((source, payload), ('snapshot', _empty('before-first-listen')))

        later = NOW + timedelta(seconds=snapshot.NON_OK_TTL_SECONDS + 60)
        payload, source = snapshot.serve(self.conn, 'user', 'daily-mix-mid', later, KEY, lambda: _payload('filled'))
        self.assertEqual((source, payload), ('live', _payload('filled')))

    def test_a_request_during_a_rebuild_reads_the_previous_row(self):
        """The build holds the key's lock; a reader that finds it held serves what is
        there rather than starting a second build or waiting out the first."""
        snapshot.serve(self.conn, 'user', 'release-radar', NOW, KEY, lambda: _payload('old'))
        later = NOW + timedelta(seconds=snapshot.RADAR_TTL_SECONDS + 5)
        lock = snapshot._lock_for('user', 'release-radar')
        lock.acquire()
        try:
            payload, source = snapshot.serve(
                self.conn, 'user', 'release-radar', later, KEY, lambda: self.fail('must not build')
            )
        finally:
            lock.release()
        self.assertEqual((source, payload), ('stale', _payload('old')))

    def test_a_request_with_nothing_to_serve_waits_for_the_build_in_progress(self):
        lock = snapshot._lock_for('user', 'daily-mix-mid')
        lock.acquire()
        result = {}

        def reader():
            result['value'] = snapshot.serve(self.conn, 'user', 'daily-mix-mid', NOW, KEY, lambda: _payload('second'))

        thread = threading.Thread(target=reader)
        thread.start()
        thread.join(timeout=0.2)
        self.assertTrue(thread.is_alive(), 'the reader should be waiting on the lock')
        # The builder finishes and writes; the waiter re-reads and finds it.
        snapshot.write(self.conn, 'user', 'daily-mix-mid', NOW.date(), NOW, KEY, _payload('first'))
        lock.release()
        thread.join(timeout=2)
        self.assertEqual(result['value'], (_payload('first'), 'snapshot'))

    def test_a_build_that_raises_releases_the_lock(self):
        def boom():
            raise RuntimeError('nope')

        with self.assertRaises(RuntimeError):
            snapshot.serve(self.conn, 'user', 'daily-mix-mid', NOW, KEY, boom)
        self.assertFalse(snapshot._lock_for('user', 'daily-mix-mid').locked())


class RefreshTest(unittest.TestCase):
    def setUp(self):
        snapshot._locks.clear()

    def test_a_pass_builds_every_missing_key_for_every_active_listener(self):
        table = _Table(listeners=['anna', 'user'])
        built = []

        def build(conn, username, slug):
            built.append((username, slug))
            return _payload(f'{username}/{slug}')

        rebuilt = snapshot.refresh_stale(table.connection(), NOW, _key, ['_list', 'release-radar'], build)
        self.assertEqual(rebuilt, 4)
        self.assertEqual(
            built, [('anna', '_list'), ('anna', 'release-radar'), ('user', '_list'), ('user', 'release-radar')]
        )

    def test_a_pass_leaves_fresh_rows_alone_and_drops_yesterday_s(self):
        table = _Table(listeners=['user'])
        conn = table.connection()
        snapshot.write(conn, 'user', 'daily-mix-mid', NOW.date(), NOW, KEY, _payload('today'))
        snapshot.write(conn, 'user', 'daily-mix-mid', (NOW - timedelta(days=1)).date(), NOW, KEY, _payload('old'))
        rebuilt = snapshot.refresh_stale(conn, NOW, _key, ['daily-mix-mid'], lambda *a: self.fail('fresh'))
        self.assertEqual(rebuilt, 0)
        self.assertEqual(list(table.rows), [('user', 'daily-mix-mid', NOW.date())])

    def test_a_pass_fills_in_a_listener_whose_mix_was_empty(self):
        """A listener who opened Home before listening holds an empty row; once they
        have listened (they are an active listener now) the pass rebuilds it after
        the short TTL, instead of leaving it empty until tomorrow."""
        table = _Table(listeners=['newcomer'])
        conn = table.connection()
        snapshot.write(conn, 'newcomer', 'daily-mix-mid', NOW.date(), NOW, KEY, _empty('before'))
        later = NOW + timedelta(seconds=snapshot.NON_OK_TTL_SECONDS + 1)
        rebuilt = snapshot.refresh_stale(conn, later, _key, ['daily-mix-mid'], lambda *a: _payload('after'))
        self.assertEqual(rebuilt, 1)
        stored = table.rows[('newcomer', 'daily-mix-mid', NOW.date())]
        self.assertEqual(json.loads(stored['payload']), _payload('after'))

    def test_a_pass_asks_for_the_key_per_listener_and_slug(self):
        """Exclusions are per listener and hardness per spectrum slug, so one key per
        pass cannot describe every row."""
        table = _Table(listeners=['anna', 'user'])
        asked = []

        def key(_conn, username, slug):
            asked.append((username, slug))
            return f'{username}/{slug}'

        snapshot.refresh_stale(table.connection(), NOW, key, ['_list', 'daily-mix-hard'], lambda *a: _payload('x'))
        self.assertEqual(
            asked, [('anna', '_list'), ('anna', 'daily-mix-hard'), ('user', '_list'), ('user', 'daily-mix-hard')]
        )
        self.assertEqual(table.rows[('user', 'daily-mix-hard', NOW.date())]['params_key'], 'user/daily-mix-hard')

    def test_a_failing_key_skips_that_row_and_not_the_pass(self):
        table = _Table(listeners=['anna', 'user'])

        def key(_conn, username, _slug):
            if username == 'anna':
                raise RuntimeError('no exclusions table')
            return KEY

        with self.assertLogs(snapshot.logger, level='ERROR'):
            rebuilt = snapshot.refresh_stale(table.connection(), NOW, key, ['release-radar'], lambda *a: _payload('x'))
        self.assertEqual(rebuilt, 1)
        self.assertEqual(list(table.rows), [('user', 'release-radar', NOW.date())])

    def test_one_listener_s_failure_does_not_stop_the_others(self):
        table = _Table(listeners=['anna', 'user'])

        def build(conn, username, slug):
            if username == 'anna':
                raise RuntimeError('anna has a broken history')
            return _payload(username)

        with self.assertLogs(snapshot.logger, level='ERROR'):
            rebuilt = snapshot.refresh_stale(table.connection(), NOW, _key, ['release-radar'], build)
        self.assertEqual(rebuilt, 1)
        self.assertIn(('user', 'release-radar', NOW.date()), table.rows)
        self.assertFalse(snapshot._lock_for('anna', 'release-radar').locked())

    def test_a_key_a_request_is_building_right_now_is_skipped(self):
        table = _Table(listeners=['user'])
        snapshot._lock_for('user', 'release-radar').acquire()
        try:
            rebuilt = snapshot.refresh_stale(table.connection(), NOW, _key, ['release-radar'], lambda *a: self.fail())
        finally:
            snapshot._lock_for('user', 'release-radar').release()
        self.assertEqual(rebuilt, 0)

    def test_the_loop_asks_for_the_params_key_per_pass(self):
        """A settings change between passes must age the rows the next pass sees."""
        table = _Table(listeners=['user'])
        keys = iter(['first', 'second'])
        with patch.object(snapshot, 'get_db_connection', side_effect=lambda: table.connection()):
            snapshot.run_feeds_refresh(
                ['release-radar'], lambda c, u, s: next(keys), lambda c, u, s: _payload(u), once=True
            )
            snapshot.run_feeds_refresh(
                ['release-radar'], lambda c, u, s: next(keys), lambda c, u, s: _payload(u), once=True
            )
        self.assertEqual(
            table.rows[('user', 'release-radar', snapshot.clock.feed_date(datetime.now()))]['params_key'], 'second'
        )


if __name__ == '__main__':
    unittest.main()
