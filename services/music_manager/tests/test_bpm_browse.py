"""The in-memory BPM index and the /api/library/bpm endpoints on top of it."""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

import services.music_manager.routers.users as users_router  # noqa: E402
from services.music_manager.api_key import resolve_system_api_key  # noqa: E402

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi.testclient import TestClient  # noqa: E402

from services.music_manager.bpm.index import BpmIndex, IndexCache  # noqa: E402
from services.music_manager.main import app  # noqa: E402
from services.music_manager.routers import bpm as bpm_router  # noqa: E402

API_KEY = resolve_system_api_key()


def row(track_id, tag=None, tempo=None, genres='', measured=None, confidence=None):
    """One INDEX_SQL row."""
    return {
        'track_id': track_id,
        'bpm_tag': tag,
        'tempo': tempo,
        'measured': measured,
        'measured_confidence': confidence,
        'measured_folded': 0,
        'genres': genres,
    }


ROWS = [
    row(1, tag=152.0, tempo=151.999, genres='Hardstyle'),  # 152, medium
    row(2, tag=76.0, genres='Raw Hardstyle'),  # folded to 152, low
    row(3, measured=150.0, confidence=0.9, genres='Hardstyle|Euphoric Hardstyle'),  # 150, high
    row(4, tempo=105.0, genres='Uptempo Hardcore'),  # 210, low
    row(5, tag=148.5, genres=''),  # 148.5, low, no genre
    row(6, tag=None, tempo=None),  # nothing usable
    row(7, tempo=161.499, genres='Hardcore'),  # 161.5, low
]


class BpmIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = BpmIndex.from_rows(ROWS)

    def ids(self, entries):
        return [e.track_id for e in entries]

    def test_rows_without_a_tempo_are_left_out(self):
        self.assertNotIn(6, self.ids(self.index.entries))
        self.assertEqual(len(self.index.entries), 6)

    def test_a_window_around_a_tempo_puts_the_nearest_first(self):
        self.assertEqual(self.ids(self.index.select(148, 152, center=150)), [3, 5, 1, 2])

    def test_equally_near_the_more_trusted_leads(self):
        # 1 (medium) and 2 (low) both read 152.
        chosen = self.index.select(151, 153, center=152)
        self.assertEqual(self.ids(chosen), [1, 2])

    def test_a_range_is_in_tempo_order(self):
        self.assertEqual(self.ids(self.index.select(140, 170)), [5, 3, 1, 2, 7])

    def test_the_bounds_are_inclusive(self):
        self.assertEqual(self.ids(self.index.select(152, 152)), [1, 2])

    def test_min_confidence_drops_the_less_trusted(self):
        self.assertEqual(self.ids(self.index.select(140, 170, min_confidence='medium')), [3, 1])
        self.assertEqual(self.ids(self.index.select(140, 170, min_confidence='high')), [3])

    def test_the_genre_filter_matches_any_of_a_tracks_genres_ignoring_case(self):
        self.assertEqual(self.ids(self.index.select(140, 170, genre='euphoric hardstyle')), [3])
        self.assertEqual(self.ids(self.index.select(140, 170, genre='HARDSTYLE')), [3, 1])

    def test_the_histogram_counts_whole_bpms_split_by_confidence(self):
        bins = {b['bpm']: b for b in self.index.histogram()}
        self.assertEqual(bins[152], {'bpm': 152, 'count': 2, 'high': 0, 'medium': 1, 'low': 1})
        self.assertEqual(bins[210]['count'], 1)
        self.assertEqual(bins[148]['count'], 1)  # 148.5 rounds to even

    def test_the_histogram_honours_its_filters(self):
        bins = self.index.histogram(min_confidence='medium', genre='Hardstyle')
        self.assertEqual([(b['bpm'], b['count']) for b in bins], [(150, 1), (152, 1)])

    def test_genre_counts_rank_the_genres(self):
        counts = {g['name']: g['count'] for g in self.index.genre_counts()}
        self.assertEqual(counts['Hardstyle'], 2)
        self.assertEqual(counts['Uptempo Hardcore'], 1)

    def test_the_summary_counts_sources(self):
        summary = self.index.summary()
        self.assertEqual(summary['tracks'], 6)
        self.assertEqual(summary['by_source'], {'tag': 3, 'analyzer': 2, 'measured': 1})


class IndexCacheTest(unittest.TestCase):
    def test_the_first_call_builds_and_later_calls_reuse(self):
        load = MagicMock(return_value=BpmIndex([]))
        cache = IndexCache(load, refresh_seconds=60, clock=lambda: 0.0)
        first = cache.get()
        self.assertIs(cache.get(), first)
        self.assertEqual(load.call_count, 1)

    def test_a_stale_index_is_served_while_it_is_rebuilt(self):
        now = [0.0]
        old, new = BpmIndex([]), BpmIndex([])
        load = MagicMock(side_effect=[old, new])
        cache = IndexCache(load, refresh_seconds=60, clock=lambda: now[0])
        self.assertIs(cache.get(), old)
        now[0] = 120.0
        with patch('services.music_manager.bpm.index.threading.Thread') as thread:
            thread.return_value.start.side_effect = cache._refresh  # pylint: disable=protected-access
            self.assertIs(cache.get(), old)
        self.assertIs(cache.get(), new)

    def test_a_failed_refresh_keeps_the_old_index(self):
        now = [0.0]
        old = BpmIndex([])
        load = MagicMock(side_effect=[old, RuntimeError('db gone')])
        cache = IndexCache(load, refresh_seconds=60, clock=lambda: now[0])
        cache.get()
        now[0] = 120.0
        cache._refresh()  # pylint: disable=protected-access
        self.assertIs(cache.get(), old)


class BpmRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        index = BpmIndex.from_rows(ROWS)
        cache_patch = patch.object(bpm_router.index_cache, 'get', return_value=index)
        cache_patch.start()
        self.addCleanup(cache_patch.stop)
        self.conn = MagicMock()
        self.cursor = self.conn.cursor.return_value.__enter__.return_value
        self.conn.cursor.return_value.__exit__.return_value = False
        self.cursor.fetchall.side_effect = lambda: [
            {
                'id': track_id,
                'title': f'Track {track_id}',
                'artist': 'Artist',
                'duration_secs': 200.0,
                'work_id': None,
                'file_path': f'/mnt/music/EPs/Label/{track_id}.mp3',
            }
            for track_id in self.cursor.execute.call_args.args[1]
        ]
        db_patch = patch.object(bpm_router, 'get_db_connection', return_value=self.conn)
        db_patch.start()
        self.addCleanup(db_patch.stop)
        tol_patch = patch.object(bpm_router, 'default_tolerance', return_value=2.0)
        tol_patch.start()
        self.addCleanup(tol_patch.stop)

    def get(self, path, **params):
        return self.client.get(path, params=params, headers=self.headers)

    def test_a_tempo_uses_the_default_tolerance(self):
        body = self.get('/api/library/bpm/tracks', bpm=150).json()
        self.assertEqual((body['bpm_from'], body['bpm_to'], body['tolerance']), (148.0, 152.0, 2.0))
        self.assertEqual([t['id'] for t in body['tracks']], [3, 5, 1, 2])
        self.assertEqual(body['total'], 4)

    def test_a_track_carries_its_bpm_its_source_and_a_library_path(self):
        track = self.get('/api/library/bpm/tracks', bpm=152, tol=0).json()['tracks'][0]
        self.assertEqual(track['library_path'], 'EPs/Label/1.mp3')
        self.assertEqual(
            {k: track[k] for k in ('bpm', 'bpm_source', 'bpm_confidence', 'bpm_folded', 'bpm_approximate')},
            {'bpm': 152.0, 'bpm_source': 'tag', 'bpm_confidence': 'medium', 'bpm_folded': False, 'bpm_approximate': True},
        )
        self.assertEqual(track['genres'], ['Hardstyle'])

    def test_a_range_with_filters(self):
        body = self.get(
            '/api/library/bpm/tracks', bpm_from=140, bpm_to=220, min_confidence='medium', genre='hardstyle'
        ).json()
        self.assertEqual([t['id'] for t in body['tracks']], [3, 1])
        self.assertIsNone(body['center'])

    def test_paging(self):
        first = self.get('/api/library/bpm/tracks', bpm_from=140, bpm_to=220, limit=2).json()
        self.assertEqual(([t['id'] for t in first['tracks']], first['next_offset']), ([5, 3], 2))
        last = self.get('/api/library/bpm/tracks', bpm_from=140, bpm_to=220, limit=2, offset=4).json()
        self.assertEqual(([t['id'] for t in last['tracks']], last['next_offset']), ([7, 4], None))

    def test_an_empty_page_asks_the_database_nothing(self):
        body = self.get('/api/library/bpm/tracks', bpm=400).json()
        self.assertEqual(body['tracks'], [])
        self.cursor.execute.assert_not_called()

    def test_a_request_needs_a_tempo_or_a_range(self):
        self.assertEqual(self.get('/api/library/bpm/tracks').status_code, 400)

    def test_an_upside_down_range_is_refused(self):
        self.assertEqual(self.get('/api/library/bpm/tracks', bpm_from=180, bpm_to=150).status_code, 400)

    def test_an_unknown_confidence_is_refused(self):
        self.assertEqual(self.get('/api/library/bpm/tracks', bpm=150, min_confidence='sure').status_code, 422)

    def test_the_histogram(self):
        body = self.get('/api/library/bpm/histogram').json()
        self.assertEqual(body['default_tolerance'], 2.0)
        self.assertIn({'bpm': 210, 'count': 1, 'high': 0, 'medium': 0, 'low': 1}, body['bins'])
        self.assertEqual(body['genres'][0], {'name': 'Hardstyle', 'count': 2})
        self.assertEqual(body['summary']['tracks'], 6)

    def test_without_a_key_it_is_unauthorized(self):
        self.assertEqual(self.client.get('/api/library/bpm/histogram').status_code, 401)


class SettingsTest(unittest.TestCase):
    def test_the_tolerance_is_clamped(self):
        with patch.object(bpm_router.settings, 'get', return_value=50):
            self.assertEqual(bpm_router.default_tolerance(), bpm_router.MAX_TOLERANCE)
        with patch.object(bpm_router.settings, 'get', return_value='junk'):
            self.assertEqual(bpm_router.default_tolerance(), bpm_router.DEFAULT_TOLERANCE)

    def test_the_reliable_confidence_is_a_percentage(self):
        with patch.object(bpm_router.settings, 'get', return_value=60):
            self.assertAlmostEqual(bpm_router.reliable_confidence(), 0.6)
        with patch.object(bpm_router.settings, 'get', return_value=None):
            self.assertAlmostEqual(bpm_router.reliable_confidence(), 0.75)

    def test_load_index_resolves_the_query_rows(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        conn.cursor.return_value.__exit__.return_value = False
        cursor.fetchall.return_value = ROWS
        with (
            patch.object(bpm_router, 'get_db_connection', return_value=conn),
            patch.object(bpm_router, 'reliable_confidence', return_value=0.75),
        ):
            index = bpm_router.load_index()
        self.assertEqual(len(index.entries), 6)
        conn.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
