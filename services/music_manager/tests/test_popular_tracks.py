"""The popular-tracks crawl: the Deezer and Last.fm clients (replaying recorded responses, never
the network), the title matcher, and one round of the worker against a fake store."""

import json
import unittest
from datetime import datetime
from pathlib import Path

from services.music_manager.popular_tracks import worker
from services.music_manager.popular_tracks.clients import (
    DEEZER,
    LASTFM,
    ArtistTopTracks,
    DeezerClient,
    LastFmClient,
    RateLimiter,
    SourceFailed,
    SourceThrottled,
    TopTrack,
)
from services.music_manager.popular_tracks.matcher import ArtistIndex, LibraryTrack, strip_brackets, title_keys

FIXTURES = Path(__file__).parent / 'fixtures' / 'popular_tracks'
NOW = datetime(2026, 9, 29, 12, 0, 0)


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class _Replay:
    """An `http_get` that answers from a queue of `(status, body)` per URL fragment."""

    def __init__(self, answers):
        self.answers = {fragment: list(queue) for fragment, queue in answers.items()}
        self.calls = []

    def __call__(self, url, params=None):
        self.calls.append((url, params))
        for fragment, queue in self.answers.items():
            if fragment in url:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f'unexpected request {url}')


def _no_wait():
    return RateLimiter(interval=0, sleep=lambda _s: None)


class DeezerClientTest(unittest.TestCase):
    def test_a_recorded_artist_resolves_and_lists_its_top_tracks(self):
        http = _Replay(
            {
                '/search/artist': [(200, _fixture('deezer_search_artist_headhunterz.json'))],
                '/artist/194172/top': [(200, _fixture('deezer_artist_top_headhunterz.json'))],
            }
        )
        result = DeezerClient(http_get=http, limiter=_no_wait()).fetch('Headhunterz')
        self.assertEqual(result.source, DEEZER)
        self.assertEqual(result.external_artist_id, '194172')
        titles = [track.title for track in result.tracks]
        # title_short, not the decorated title: "(Original Mix)" is gone, the anthem context stays.
        self.assertIn('Disrespect', titles)
        self.assertIn('Scrap Attack (Defqon.1 2009 anthem)', titles)
        self.assertEqual(result.tracks[0].position, 1)
        self.assertEqual(result.tracks[0].popularity, 481354)
        # Only the artist name went out.
        self.assertEqual(http.calls[0][1], {'q': 'Headhunterz', 'limit': 5})

    def test_only_an_exact_name_match_counts(self):
        http = _Replay({'/search/artist': [(200, {'data': [{'id': 1, 'name': 'Headhunterz & Wildstylez'}]})]})
        result = DeezerClient(http_get=http, limiter=_no_wait()).fetch('Headhunterz')
        self.assertIsNone(result.external_artist_id)
        self.assertEqual(result.tracks, [])
        self.assertEqual(len(http.calls), 1)

    def test_a_quota_error_is_retried_with_backoff(self):
        quota = (200, {'error': {'type': 'Exception', 'message': 'Quota limit exceeded', 'code': 4}})
        http = _Replay({'/search/artist': [quota, (200, _fixture('deezer_search_artist_headhunterz.json'))]})
        slept = []
        client = DeezerClient(http_get=http, limiter=_no_wait(), sleep=slept.append)
        self.assertEqual(client.find_artist('Headhunterz'), '194172')
        self.assertEqual(slept, [5.0])
        self.assertEqual(client.requests, 2)

    def test_a_source_that_keeps_refusing_raises_throttled(self):
        slept = []
        client = DeezerClient(http_get=_Replay({'/search': [(429, None)]}), limiter=_no_wait(), sleep=slept.append)
        with self.assertRaises(SourceThrottled):
            client.find_artist('Angerfist')
        self.assertEqual(slept, [5.0, 10.0, 20.0])

    def test_a_server_error_is_a_failure_not_a_retry(self):
        client = DeezerClient(http_get=_Replay({'/search': [(502, None)]}), limiter=_no_wait())
        with self.assertRaises(SourceFailed):
            client.find_artist('Angerfist')


class LastFmClientTest(unittest.TestCase):
    def test_a_recorded_top_list_is_read_in_lastfms_order(self):
        http = _Replay({'audioscrobbler': [(200, _fixture('lastfm_artist_toptracks_angerfist.json'))]})
        result = LastFmClient('key', http_get=http, limiter=_no_wait()).fetch('Angerfist')
        self.assertEqual(result.source, LASTFM)
        self.assertEqual([track.title for track in result.tracks][:2], ['Pennywise', 'Incarnation'])
        self.assertEqual([track.position for track in result.tracks], [1, 2, 3])
        self.assertEqual(result.tracks[0].popularity, 61234)
        self.assertEqual(http.calls[0][1]['artist'], 'Angerfist')

    def test_an_unknown_artist_is_an_answer_not_a_failure(self):
        http = _Replay(
            {'audioscrobbler': [(400, {'error': 6, 'message': 'The artist you supplied could not be found'})]}
        )
        result = LastFmClient('key', http_get=http, limiter=_no_wait()).fetch('Nobody')
        self.assertIsNone(result.external_artist_id)

    def test_rate_limit_error_29_backs_off(self):
        http = _Replay({'audioscrobbler': [(200, {'error': 29})]})
        client = LastFmClient('key', http_get=http, limiter=_no_wait(), sleep=lambda _s: None)
        with self.assertRaises(SourceThrottled):
            client.fetch('Angerfist')


class RateLimiterTest(unittest.TestCase):
    def test_calls_are_spaced_by_the_interval(self):
        now = [100.0]
        slept = []

        def sleep(seconds):
            slept.append(round(seconds, 3))
            now[0] += seconds

        limiter = RateLimiter(interval=0.25, clock=lambda: now[0], sleep=sleep)
        limiter.wait()
        now[0] += 0.1
        limiter.wait()
        limiter.wait()
        self.assertEqual(slept, [0.15, 0.25])


class MatcherTest(unittest.TestCase):
    def setUp(self):
        self.index = ArtistIndex(
            [
                LibraryTrack(1, 'uid-1', 'Scrap Attack', work_id=10, canonical_track_id=2),
                LibraryTrack(2, 'uid-2', 'Scrap Attack (Original Mix)', work_id=10, canonical_track_id=2),
                LibraryTrack(3, 'uid-3', 'Pennywise', work_id=11),
                LibraryTrack(4, 'uid-4', "Don't Stop", work_id=None),
            ]
        )

    def test_keys_go_from_strict_to_loose(self):
        self.assertEqual(title_keys('Pennywise (Radio Edit)'), ['pennywise radio edit', 'pennywise'])
        self.assertEqual(strip_brackets('World Of Madness (Defqon.1 (2012) Anthem)'), 'World Of Madness')

    def test_a_version_suffix_and_an_anthem_label_still_find_the_song(self):
        self.assertEqual(self.index.match('Pennywise (Radio Edit)').track.track_uid, 'uid-3')
        match = self.index.match('Scrap Attack (Defqon.1 2009 anthem)')
        # The work's canonical is the version stored.
        self.assertEqual(match.track.id, 2)
        self.assertGreater(match.strictness, 0)

    def test_spelling_differences_fold_away(self):
        self.assertEqual(self.index.match('DONT STOP').track.id, 4)

    def test_an_unknown_title_matches_nothing(self):
        self.assertIsNone(self.index.match('Solid Stigma'))


class _FakeStore:
    def __init__(self, due):
        self.due = due
        self.saved = []
        self.failures = []

    def due_artists(self, source, config, now):
        return list(self.due.get(source, []))

    def artist_tracks(self, artist_key):
        return [LibraryTrack(1, 'uid-1', 'Pennywise', work_id=5)]

    def save(self, artist_key, name, result, index, now):
        matched = sum(1 for track in result.tracks if index.match(track.title))
        self.saved.append((artist_key, result.source, result.external_artist_id, matched))
        return len(result.tracks), matched

    def record_failure(self, artist_key, name, source, now):
        self.failures.append((artist_key, source))


class _FakeClient:
    def __init__(self, answers):
        self.answers = answers
        self.requests = 0

    def fetch(self, name):
        self.requests += 1
        answer = self.answers[name]
        if isinstance(answer, Exception):
            raise answer
        return answer


CONFIG = {'enabled': True, 'refresh_days': 7, 'max_artists': 10, 'min_listens': 5, 'max_minutes': 30}


class WorkerRoundTest(unittest.TestCase):
    def test_a_round_fetches_matches_and_records_failures(self):
        store = _FakeStore({DEEZER: [('angerfist', 'Angerfist'), ('nobody', 'Nobody'), ('flaky', 'Flaky')]})
        client = _FakeClient(
            {
                'Angerfist': ArtistTopTracks(DEEZER, '1', [TopTrack('9', 'Pennywise', 1, 100)]),
                'Nobody': ArtistTopTracks(DEEZER, None, []),
                'Flaky': SourceFailed('HTTP 502'),
            }
        )
        result = worker.run_round(CONFIG, store, {DEEZER: client}, now=lambda: NOW)
        self.assertEqual(store.saved, [('angerfist', DEEZER, '1', 1), ('nobody', DEEZER, None, 0)])
        self.assertEqual(store.failures, [('flaky', DEEZER)])
        self.assertEqual(result.fetched[DEEZER], 1)
        self.assertEqual(result.not_found[DEEZER], 1)
        self.assertEqual(result.failed[DEEZER], 1)
        self.assertEqual(result.matched[DEEZER], 1)

    def test_a_throttled_source_ends_its_part_of_the_round_but_not_the_others(self):
        store = _FakeStore({DEEZER: [('a', 'A'), ('b', 'B')], LASTFM: [('a', 'A')]})
        deezer = _FakeClient({'A': SourceThrottled('quota'), 'B': ArtistTopTracks(DEEZER, '2', [])})
        lastfm = _FakeClient({'A': ArtistTopTracks(LASTFM, 'a', [TopTrack('x', 'Pennywise', 1, 5)])})
        result = worker.run_round(CONFIG, store, {DEEZER: deezer, LASTFM: lastfm}, now=lambda: NOW)
        self.assertEqual(result.throttled, [DEEZER])
        self.assertEqual(deezer.requests, 1)
        self.assertEqual(store.saved, [('a', LASTFM, 'a', 1)])

    def test_a_round_stops_at_its_deadline(self):
        store = _FakeStore({DEEZER: [('a', 'A'), ('b', 'B')]})
        ticks = iter([0.0, 0.0, 99999.0])
        client = _FakeClient({'A': ArtistTopTracks(DEEZER, '1', []), 'B': ArtistTopTracks(DEEZER, '2', [])})
        result = worker.run_round(CONFIG, store, {DEEZER: client}, now=lambda: NOW, clock=lambda: next(ticks))
        self.assertTrue(result.stopped_early)
        self.assertEqual(len(store.saved), 1)


class WorkerSettingsTest(unittest.TestCase):
    def test_lastfm_is_only_used_with_a_key(self):
        self.assertEqual(set(worker.build_clients({'lastfm_api_key': ''})), {DEEZER})
        self.assertEqual(set(worker.build_clients({'lastfm_api_key': 'k'})), {DEEZER, LASTFM})

    def test_settings_fall_back_on_garbage(self):
        config = worker.settings_snapshot({'popular_tracks_enabled': 'off', 'popular_tracks_max_artists': 'x'})
        self.assertFalse(config['enabled'])
        self.assertEqual(config['max_artists'], worker.DEFAULT_MAX_ARTISTS)
        self.assertEqual(config['lastfm_api_key'], '')

    def test_a_switched_off_loop_does_no_round(self):
        def boom(_config):
            raise AssertionError('no clients when switched off')

        seconds = worker.popular_tracks_tick({'popular_tracks_enabled': False}, clients_factory=boom)
        self.assertEqual(seconds, worker.CHECK_EVERY_SECONDS)


class _Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((' '.join(sql.split()), params))

    def executemany(self, sql, seq):
        self.executed.append((' '.join(sql.split()), list(seq)))

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False
        self.log = []

    def cursor(self):
        return self._cursor

    def begin(self):
        self.log.append('BEGIN')

    def commit(self):
        self.log.append('COMMIT')

    def rollback(self):
        self.log.append('ROLLBACK')

    def close(self):
        self.closed = True


class WorkerStoreTest(unittest.TestCase):
    def test_save_replaces_the_list_in_one_transaction_with_the_match(self):
        cursor = _Cursor()
        conn = _Conn(cursor)
        store = worker.PopularTracksStore(connect=lambda: conn)
        index = ArtistIndex([LibraryTrack(7, 'uid-7', 'Pennywise', work_id=70)])
        result = ArtistTopTracks(
            DEEZER, '1', [TopTrack('9', 'Pennywise (Radio Edit)', 1, 100), TopTrack('8', 'X', 2, 50)]
        )
        self.assertEqual(store.save('angerfist', 'Angerfist', result, index, NOW), (2, 1))
        self.assertEqual(conn.log, ['BEGIN', 'COMMIT'])
        statements = [sql for sql, _ in cursor.executed]
        self.assertTrue(statements[0].startswith('DELETE FROM artist_popular_tracks'))
        inserted = cursor.executed[1][1]
        self.assertEqual(inserted[0][7:9], ('uid-7', 70))
        self.assertEqual(inserted[1][7:9], (None, None))
        self.assertEqual(cursor.executed[2][1][4], 'ok')
        self.assertTrue(conn.closed)

    def test_due_artists_passes_the_cutoffs_and_the_limit(self):
        cursor = _Cursor([{'artist_key': 'angerfist', 'name': 'Angerfist'}])
        store = worker.PopularTracksStore(connect=lambda: _Conn(cursor))
        self.assertEqual(store.due_artists(DEEZER, CONFIG, NOW), [('angerfist', 'Angerfist')])
        params = cursor.executed[0][1]
        self.assertEqual(params[0], 5)
        self.assertEqual(params[1], DEEZER)
        self.assertEqual(params[2], datetime(2026, 9, 22, 12, 0, 0))
        self.assertEqual(params[4], 10)


if __name__ == '__main__':
    unittest.main()
