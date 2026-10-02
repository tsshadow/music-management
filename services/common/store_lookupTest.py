"""The Deezer album lookup and its cache, with recorded answers and no network or database."""

import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from services.common.release_nfo import StoreLink
from services.common.store_lookup import (
    NOT_FOUND,
    OK,
    Budget,
    StoreAlbum,
    StoreCache,
    StoreThrottled,
    _Pace,
    fetch_deezer,
)

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
LINK = StoreLink('deezer', '1104265012', 'https://deezer.com/album/1104265012')
# The answer api.deezer.com gave on 2026-10-02, cut to the fields that matter.
MINUS_MILITIA = {
    'id': 1104265012,
    'title': 'Recover The Archive (Hard Bass 2026 Anthem)',
    'upc': '8719244873593',
    'label': 'b2s Records',
    'release_date': '2026-10-02',
}


class FakeDb:
    """`release_store_lookups` as a dict, behind the connection/cursor shape the cache uses."""

    def __init__(self, fail=False):
        self.rows = {}
        self.fail = fail
        self.reads = 0

    @contextmanager
    def connection(self):
        if self.fail:
            raise ConnectionError('db down')
        db = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params):
                if sql.startswith('SELECT'):
                    db.reads += 1
                    self.row = db.rows.get(params)
                else:
                    db.rows[(params[0], params[1])] = params[2:]

            def fetchone(self):
                return self.row

        class Connection:
            def cursor(self):
                return Cursor()

            def commit(self):
                pass

        yield Connection()


def no_pace():
    return _Pace(0, clock=lambda: 0.0, sleep=lambda _s: None)


class FetchDeezerTest(unittest.TestCase):
    def test_a_found_album(self):
        album = fetch_deezer('1104265012', http_get=lambda url: (200, MINUS_MILITIA), pace=no_pace(), now=NOW)

        self.assertEqual(OK, album.status)
        self.assertEqual(('b2s Records', '8719244873593', '2026-10-02'), (album.label, album.upc, album.full_date))

    def test_no_data_is_a_gone_album(self):
        body = {'error': {'type': 'DataException', 'message': 'no data', 'code': 800}}
        album = fetch_deezer('1', http_get=lambda url: (200, body), pace=no_pace(), now=NOW)

        self.assertEqual(NOT_FOUND, album.status)

    def test_a_quota_refusal_raises(self):
        body = {'error': {'type': 'Exception', 'message': 'Quota limit exceeded', 'code': 4}}
        with self.assertRaises(StoreThrottled):
            fetch_deezer('1', http_get=lambda url: (200, body), pace=no_pace())

    def test_a_network_error_is_none(self):
        def down(url):
            raise OSError('no route to host')

        self.assertIsNone(fetch_deezer('1', http_get=down, pace=no_pace()))

    def test_a_zero_date_is_not_a_full_date(self):
        self.assertIsNone(StoreAlbum('deezer', '1', OK, release_date='0000-00-00').full_date)


class StoreCacheTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.calls = []

    def cache(self, answer=(200, MINUS_MILITIA)):
        def http_get(url):
            self.calls.append(url)
            if isinstance(answer, Exception):
                raise answer
            return answer

        return StoreCache(self.db.connection, http_get=http_get, pace=no_pace(), clock=lambda: NOW)

    def test_without_a_budget_nothing_goes_over_the_network(self):
        self.assertIsNone(self.cache().lookup(LINK))
        self.assertEqual([], self.calls)

    def test_a_fetched_album_is_stored_and_read_back_by_another_process(self):
        album = self.cache().lookup(LINK, Budget(5))

        self.assertEqual('2026-10-02', album.full_date)
        self.assertEqual(1, len(self.calls))
        again = self.cache().lookup(LINK, Budget(5))
        self.assertEqual('b2s Records', again.label)
        self.assertEqual(1, len(self.calls))

    def test_the_budget_is_spent_and_respected(self):
        budget = Budget(1)
        self.cache().lookup(LINK, budget)
        self.assertFalse(budget.allows())
        other = StoreLink('deezer', '2', 'https://deezer.com/album/2')
        self.assertIsNone(self.cache().lookup(other, budget))
        self.assertEqual(1, len(self.calls))

    def test_a_throttled_store_ends_the_budget(self):
        budget = Budget(10)
        quota = (200, {'error': {'code': 4}})

        self.assertIsNone(self.cache(quota).lookup(LINK, budget))
        self.assertTrue(budget.throttled)
        self.assertFalse(budget.allows())

    def test_a_network_failure_is_not_stored(self):
        self.assertIsNone(self.cache(OSError('down')).lookup(LINK, Budget(5)))
        self.assertEqual({}, self.db.rows)

    def test_a_gone_album_is_asked_again_after_thirty_days(self):
        old = (NOW - timedelta(days=31)).replace(tzinfo=None)
        self.db.rows[('deezer', '1104265012')] = (NOT_FOUND, None, None, None, None, old)

        album = self.cache().lookup(LINK, Budget(5))

        self.assertEqual(OK, album.status)
        self.assertEqual(1, len(self.calls))

    def test_a_recent_gone_album_is_not_asked_again(self):
        self.db.rows[('deezer', '1104265012')] = (NOT_FOUND, None, None, None, None, NOW.replace(tzinfo=None))

        album = self.cache().lookup(LINK, Budget(5))

        self.assertEqual(NOT_FOUND, album.status)
        self.assertEqual([], self.calls)

    def test_an_unreachable_database_still_answers_from_the_store(self):
        self.db.fail = True
        album = self.cache().lookup(LINK, Budget(5))
        self.assertEqual('2026-10-02', album.full_date)

    def test_other_stores_are_never_asked(self):
        link = StoreLink('beatport', '4567890', 'https://www.beatport.com/release/x/4567890')
        self.assertIsNone(self.cache().lookup(link, Budget(5)))
        self.assertEqual([], self.calls)

    def test_the_memory_layer_saves_the_table_a_read_per_track(self):
        cache = self.cache()
        cache.lookup(LINK)
        cache.lookup(LINK)
        self.assertEqual(1, self.db.reads)


if __name__ == '__main__':
    unittest.main()
