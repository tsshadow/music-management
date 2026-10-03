"""The dry-run-first backfill of year-only release dates in the label tree."""

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

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


def connection_with(paths, dated=()):
    """A connection whose cursor answers the year-only query with `paths`, the full-date one with `dated`."""
    cursor = MagicMock()
    last = {}
    cursor.execute.side_effect = lambda sql, params=None: last.update(sql=sql)
    cursor.fetchall.side_effect = lambda: (
        list(dated) if last.get('sql') == backfill.DATED_SQL else [(path,) for path in paths]
    )
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


# Full-date releases: the rip-dated B2S single now has a Deezer answer, a street-dated release has
# an arrival-dated track, and a Deezer link nobody has asked about yet.
B2S_DATED = f'{EPS}/B2S/Minus_Militia_-_Other_Track-SINGLE-WEB-2026-UTNG'
STREET_DATED = f'{EPS}/Scantraxx/SCAN125 - X_-_W-(SCAN125)-WEB-2026-ZzZz'
PENDING_DATED = f'{EPS}/Rawcore/RAW048 - Rawcore_-_Late-(RAW048)-WEB-2026'

DATED_NFOS = {
    B2S_DATED: NFOS[B2S],
    STREET_DATED: 'Str.date : 16-01-2026\n',
    PENDING_DATED: 'Rip.date: 03.03.2026\nUrl.....: https://www.deezer.com/en/album/93254283\n',
}


class UpgradeTest(unittest.TestCase):
    """Full-date tracks on a lower rung than their release offers now."""

    def setUp(self):
        tags = backfill.DateTags
        self.sources = {
            f'{B2S_DATED}/01.mp3': 'nfo-rip',
            f'{B2S_DATED}/02.mp3': 'arrival',
            f'{B2S_DATED}/03.mp3': tags('', '2026-09-15'),  # a person's date: not the .nfo's
            f'{B2S_DATED}/07.mp3': tags('', '2026-10-01'),  # the .nfo rip date, from before the ladder
            f'{B2S_DATED}/04.mp3': 'deezer',  # an equal rung with another date
            f'{B2S_DATED}/05.mp3': 'tag',
            f'{B2S_DATED}/06.mp3': 'nfo-rip',  # its date already equals Deezer's
            f'{STREET_DATED}/01.mp3': 'arrival',
            f'{STREET_DATED}/02.mp3': 'nfo-rip',
            f'{STREET_DATED}/03.mp3': 'deezer',  # better than the .nfo: never downgraded
            f'{PENDING_DATED}/01.mp3': 'nfo-rip',
        }
        dates = {f'{B2S_DATED}/06.mp3': '2026-10-02', f'{B2S_DATED}/04.mp3': '2026-09-30'}
        dated = [(path, dates.get(path, '2026-10-01')) for path in self.sources]
        self.connection, self.cursor = connection_with([], dated)
        self.store = FakeStore()
        self.read = {**NFOS, **DATED_NFOS}.get
        self.queue = ImportQueue(f'{EPS}/__TODO')
        self.read_paths = []

    def read_source(self, path):
        self.read_paths.append(path)
        found = self.sources[path]
        return found if isinstance(found, backfill.DateTags) else backfill.DateTags(found, '2026-10-01')

    def run_backfill(self, **kwargs):
        return backfill.run(
            self.connection, EPS, self.queue, self.store, read_nfo=self.read, read_tags=self.read_source, **kwargs
        )

    def test_the_dry_run_counts_each_lower_rung_on_its_own(self):
        report = self.run_backfill()

        self.assertEqual(
            {
                'upgrade-from-nfo-rip': {'tracks': 3, 'directories': 2},
                'upgrade-from-arrival': {'tracks': 2, 'directories': 2},
                'upgrade-from-tag': {'tracks': 1, 'directories': 1},
                'upgrade-pending': {'tracks': 1, 'directories': 1},
            },
            report['counts'],
        )
        self.assertEqual(11, report['dated_tracks'])
        self.assertEqual(7, report['upgrade_tracks'])
        self.assertEqual(6, report['liftable_tracks'])
        self.cursor.executemany.assert_not_called()

    def test_never_a_downgrade_nor_an_unknown_or_equal_date(self):
        liftable = set(
            backfill.plan_upgrades(
                backfill.dated_candidates(self.cursor, EPS, self.queue), self.store, self.read, self.read_source
            ).liftable()
        )

        for kept in ('03', '04', '06'):
            self.assertNotIn(f'{B2S_DATED}/{kept}.mp3', liftable)
        self.assertIn(f"{STREET_DATED}/02.mp3", liftable)  # nfo-rip under an .nfo street date
        self.assertNotIn(f'{STREET_DATED}/03.mp3', liftable)

    def test_a_date_equal_to_the_best_one_is_not_even_read(self):
        self.run_backfill()
        self.assertNotIn(f'{B2S_DATED}/06.mp3', self.read_paths)
        self.assertEqual(len(set(self.read_paths)), len(self.read_paths))

    def test_apply_queues_the_upgrades_with_the_reason(self):
        report = self.run_backfill(apply=True)

        queued = sorted(row[0] for call in self.cursor.executemany.call_args_list for row in call.args[1])
        expected = sorted(
            [
                f'{B2S_DATED}/01.mp3',
                f'{B2S_DATED}/02.mp3',
                f'{B2S_DATED}/05.mp3',
                f'{B2S_DATED}/07.mp3',
                f'{STREET_DATED}/01.mp3',
                f'{STREET_DATED}/02.mp3',
            ]
        )
        self.assertEqual(expected, queued)
        self.assertEqual(6, report['queued'])

    def test_lookup_asks_for_the_pending_release_and_lifts_it(self):
        report = self.run_backfill(lookup=10)

        self.assertEqual(['93254283'], self.store.fetched)
        self.assertNotIn('upgrade-pending', report['counts'])
        self.assertEqual({'tracks': 4, 'directories': 3}, report['counts']['upgrade-from-nfo-rip'])

    def test_a_pending_release_is_asked_even_when_the_date_equals_the_nfo(self):
        self.connection, self.cursor = connection_with([], [(f'{PENDING_DATED}/01.mp3', '2026-03-03')])

        report = self.run_backfill(lookup=10)

        self.assertEqual(['93254283'], self.store.fetched)
        self.assertEqual({'upgrade-from-nfo-rip': {'tracks': 1, 'directories': 1}}, report['counts'])


# OMA writes its .nfo dates month-first; rules_scene_group_date_format says so. Production, 2026-10-03:
# `Rip.date: 05.09.2022`, Deezer 2022-05-06, so the release is from May, not September.
OMA = f'{EPS}/BSC/BSC040 - VA-Devotions_Chapter_1-()-WEB-2022-OMA'


class FakeFormats:
    """`rules_scene_group_date_format` as the rule's LookupTableHelper answers it, case-insensitively."""

    def get(self, group):
        return ['md'] if group.lower() == 'oma' else []


class SceneGroupDateOrderTest(unittest.TestCase):
    """The backfill reads an .nfo date in the scene group's own order, as the rule does."""

    def setUp(self):
        self.read = {OMA: 'Rip.date: 05.09.2022\n'}.get
        self.store = FakeStore()

    def test_a_month_first_group_is_read_month_first(self):
        best = backfill.best_available(OMA, self.store, self.read, FakeFormats())

        self.assertEqual(('nfo-rip', '2022-05-09'), (best.verdict, best.date))

    def test_without_the_table_the_default_order_applies(self):
        self.assertEqual('2022-09-05', backfill.best_available(OMA, self.store, self.read).date)

    def test_the_rules_own_date_is_its_rung_and_the_swapped_one_is_not(self):
        best = backfill.best_available(OMA, self.store, self.read, FakeFormats())

        self.assertEqual('nfo-rip', backfill.DateTags('', '2022-05-09', '2022').rung(best))
        self.assertEqual('', backfill.DateTags('', '2022-09-05', '2022').rung(best))

    def run_with_deezer(self, formats):
        """The OMA release with a cached Deezer date, one year-only track and one with the rule's .nfo date."""
        self.store.cached_albums['555'] = StoreAlbum('deezer', '555', OK, release_date='2022-05-06')
        read = {OMA: 'Rip.date: 05.09.2022\nUrl:https://deezer.com/album/555\n'}.get
        connection, _cursor = connection_with([f'{OMA}/01.mp3'], [(f'{OMA}/02.mp3', '2022-05-09')])
        return backfill.run(
            connection,
            EPS,
            ImportQueue(f'{EPS}/__TODO'),
            self.store,
            read_nfo=read,
            read_tags=lambda path: backfill.DateTags('', '2022-05-09', '2022'),
            formats=formats,
        )

    def test_run_passes_the_table_to_both_plans(self):
        report = self.run_with_deezer(FakeFormats())

        self.assertEqual(
            {
                'deezer': {'tracks': 1, 'directories': 1},
                'upgrade-from-nfo-rip': {'tracks': 1, 'directories': 1},
            },
            report['counts'],
        )

    def test_without_the_table_the_rules_date_reads_as_a_persons(self):
        self.assertNotIn('upgrade-from-nfo-rip', self.run_with_deezer(None)['counts'])

    def test_date_order_without_a_group_or_a_table(self):
        self.assertIsNone(backfill.date_order('No_Group_Here', FakeFormats()))
        self.assertIsNone(backfill.date_order('X-WEB-2022-OMA', None))
        self.assertEqual('md', backfill.date_order('X-WEB-2022-OMA', FakeFormats()))


class ReadDateSourceTest(unittest.TestCase):
    """The tag is found under its key for every format family."""

    def read(self, tags):
        audio = MagicMock()
        audio.tags = tags
        with patch.object(backfill.mutagen, 'File', return_value=audio):
            return backfill.read_date_tags('/x.mp3').source

    def test_id3_vorbis_and_mp4(self):
        frame = MagicMock()
        frame.text = ['nfo-rip']
        self.assertEqual('nfo-rip', self.read({'TXXX:DATE_SOURCE': frame}))
        self.assertEqual('arrival', self.read({'date_source': ['arrival']}))
        self.assertEqual('tag', self.read({'----:com.apple.iTunes:date_source': [b'tag']}))

    def test_no_tag_or_an_unreadable_file_is_empty(self):
        self.assertEqual('', self.read({}))
        with patch.object(backfill.mutagen, 'File', side_effect=OSError('gone')):
            self.assertEqual(backfill.DateTags(), backfill.read_date_tags('/x.mp3'))

    def test_the_dates_beside_the_source(self):
        audio = MagicMock()
        audio.tags = {'TDOR': MagicMock(text=['2023-01-10']), 'TDRC': MagicMock(text=['2023'])}
        with patch.object(backfill.mutagen, 'File', return_value=audio):
            self.assertEqual(backfill.DateTags('', '2023-01-10', '2023'), backfill.read_date_tags('/x.mp3'))


if __name__ == '__main__':
    unittest.main()
