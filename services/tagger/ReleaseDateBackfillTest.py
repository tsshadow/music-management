"""The dry-run-first backfill of year-only release dates in the label tree."""

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock

from services.common.import_queue import ImportQueue
from services.common.release_nfo import StoreLink
from services.common.store_lookup import NOT_FOUND, OK, StoreAlbum
from services.tagger import release_date_backfill as backfill

EPS = '/mnt/music/EPs'
B2S = f'{EPS}/B2S/Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)-SINGLE-WEB-2026-UTNG'
STREET = f'{EPS}/Scantraxx/SCAN123 - X_-_Y-(SCAN123)-WEB-2026-ZzZz'
BARE = f'{EPS}/Scantraxx/SCAN124 - X_-_Z-(SCAN124)-WEB-2026-ZzZz'
PENDING = f'{EPS}/Rawcore/RAW046 - Rawcore_-_Love-(RAW046)-WEB-2026'
GONE = f'{EPS}/Rawcore/RAW047 - Rawcore_-_Gone-(RAW047)-WEB-2026'
QUEUED = f'{EPS}/__TODO/ - Guizcore_-_Coffee_Time-WEB-FLAC-2026'

NFOS = {
    B2S: 'Rip.date: 01.10.2026\nUrl:https://deezer.com/album/1104265012\n',
    STREET: 'Str.date : 16-01-2026\n',
    BARE: 'Genre....: Hardstyle\n',
    PENDING: 'Url.....: https://www.deezer.com/en/album/93254283\n',
    GONE: 'Url.....: https://www.deezer.com/album/111\n',
}


class FakeStore:
    """Answers from a dict; a budgeted lookup 'fetches' from `remote`."""

    def __init__(self):
        self.cached_albums = {
            '1104265012': StoreAlbum('deezer', '1104265012', OK, 'b2s Records', '8719244873593', '2026-10-02'),
            '111': StoreAlbum('deezer', '111', NOT_FOUND, fetched_at=datetime.now(UTC)),
        }
        self.remote = {'93254283': StoreAlbum('deezer', '93254283', OK, release_date='2026-02-20')}
        self.fetched = []

    def lookup(self, link: StoreLink, budget=None):
        if link.album_id in self.cached_albums:
            return self.cached_albums[link.album_id]
        if budget is None or not budget.allows():
            return None
        budget.spend()
        self.fetched.append(link.album_id)
        album = self.remote.get(link.album_id)
        if album:
            self.cached_albums[link.album_id] = album
        return album

    def is_stale(self, album):
        return False


def connection_with(paths):
    cursor = MagicMock()
    cursor.fetchall.return_value = [(path,) for path in paths]
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection, cursor


class BackfillTest(unittest.TestCase):
    def setUp(self):
        self.paths = [f'{d}/01.mp3' for d in (B2S, STREET, BARE, PENDING, GONE, QUEUED)] + [f'{B2S}/02.mp3']
        self.connection, self.cursor = connection_with(self.paths)
        self.store = FakeStore()
        self.read = NFOS.get
        self.queue = ImportQueue(f'{EPS}/__TODO')

    def run_backfill(self, **kwargs):
        return backfill.run(self.connection, EPS, self.queue, self.store, read_nfo=self.read, **kwargs)

    def test_the_dry_run_counts_per_rung_and_writes_nothing(self):
        report = self.run_backfill()

        self.assertEqual(
            {
                'deezer': {'tracks': 2, 'directories': 1},
                'nfo-street': {'tracks': 1, 'directories': 1},
                'none': {'tracks': 1, 'directories': 1},
                'deezer-pending': {'tracks': 1, 'directories': 1},
                'deezer-gone': {'tracks': 1, 'directories': 1},
            },
            report['counts'],
        )
        self.assertEqual(3, report['liftable_tracks'])
        self.assertEqual(0, report['queued'])
        self.assertEqual([], self.store.fetched)
        self.cursor.executemany.assert_not_called()

    def test_the_import_queue_is_left_out(self):
        report = self.run_backfill()
        self.assertEqual(6, report['tracks'])

    def test_lookup_fills_the_cache_and_lifts_the_pending_release(self):
        report = self.run_backfill(lookup=10)

        self.assertEqual(['93254283'], self.store.fetched)
        self.assertEqual({'asked': 1, 'throttled': 0}, report['lookup'])
        self.assertEqual({'tracks': 3, 'directories': 2}, report['counts']['deezer'])
        self.assertNotIn('deezer-pending', report['counts'])
        self.assertEqual(4, report['liftable_tracks'])

    def test_apply_queues_only_the_liftable_tracks_with_the_reason(self):
        report = self.run_backfill(apply=True)

        queued = [row[0] for call in self.cursor.executemany.call_args_list for row in call.args[1]]
        self.assertEqual(sorted([f'{B2S}/01.mp3', f'{B2S}/02.mp3', f'{STREET}/01.mp3']), sorted(queued))
        reasons = {row[1] for call in self.cursor.executemany.call_args_list for row in call.args[1]}
        self.assertEqual({'release_date_ladder'}, reasons)
        self.assertEqual(3, report['queued'])
        self.connection.commit.assert_called_once()

    def test_a_cached_date_from_another_year_is_not_a_lift(self):
        self.store.cached_albums['1104265012'] = StoreAlbum('deezer', '1104265012', OK, release_date='2019-01-01')
        report = self.run_backfill()
        self.assertEqual({'tracks': 2, 'directories': 1}, report['counts']['nfo-rip'])


if __name__ == '__main__':
    unittest.main()
