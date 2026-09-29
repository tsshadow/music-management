"""build_old_hits against a scripted cursor, and the router's dispatch to it.

The rows are shaped like the SELECT lists in feeds/old_hits_queries.py and
feeds/queries.canonical_rows_query, so a renamed column fails here rather than in production.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from services.music_manager.feeds.old_hits import OldHitsConfig
from services.music_manager.feeds.old_hits_build import build_old_hits
from services.music_manager.routers import feeds as feeds_router
from services.music_manager.tests.scripted_cursor import ScriptedCursor

NOW = datetime(2026, 9, 29, 12, 0, 0)


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _display(track_id, artist, label=None, genres='', duration=300):
    return {
        'id': track_id,
        'title': f'Song {track_id}',
        'track_uid': f'uid-{track_id}',
        'artist': artist,
        'duration_secs': duration,
        'work_id': None,
        'canonical_track_id': None,
        'heard': 0,
        'label': label,
        'has_label': 1 if label else 0,
        'genres': genres,
        'file_path': f'/mnt/music/{track_id}.mp3',
        'bpm': None,
        'release_year': None,
        'release_date': '2009-01-01',
        'is_soundcloud': 0,
        'rating': None,
    }


def _rules(exclusions=()):
    # The display rows first: canonical_rows_query also mentions scrobble_listens and
    # rating_tracks (the song-level heard and rating), which the later fragments look for.
    return [
        (
            'AND t.id IN (',
            None,
            [
                _display(1, 'Headhunterz'),
                _display(2, 'Somebody'),
                _display(3, 'Headhunterz'),
                _display(4, 'Angerfist', genres='Hardcore,Terror'),
                _display(5, 'Headhunterz'),
                _display(6, 'Headhunterz', label='Scantraxx'),
            ],
        ),
        (
            'FROM rating_tracks r',
            None,
            [
                {'track_id': 1, 'work_id': 100, 'canonical_track_id': 1, 'artist_id': 10, 'rating': 5},
                {'track_id': 2, 'work_id': None, 'canonical_track_id': None, 'artist_id': 20, 'rating': 1},
                {'track_id': 3, 'work_id': 300, 'canonical_track_id': 3, 'artist_id': 10, 'rating': 4},
            ],
        ),
        (
            'FROM scrobble_listens s',
            None,
            [
                {
                    'song': 400,
                    'work_id': 400,
                    'track_id': 4,
                    'canonical_track_id': 4,
                    'artist_id': 30,
                    'plays': 8,
                    'last_heard': NOW - timedelta(days=300),
                },
                {
                    'song': 500,
                    'work_id': 500,
                    'track_id': 5,
                    'canonical_track_id': 5,
                    'artist_id': 10,
                    'plays': 5,
                    'last_heard': NOW - timedelta(days=10),
                },
            ],
        ),
        (
            'FROM artist_popular_tracks p',
            None,
            [
                {
                    'source': 'deezer',
                    'position': 1,
                    'track_id': 6,
                    'work_id': 600,
                    'canonical_track_id': 6,
                    'artist_id': 10,
                }
            ],
        ),
        ('HAVING COUNT(*) >= %s', None, []),
        (
            'WHERE t.work_id IN (',
            None,
            [
                {'work_id': 100, 'earliest_date': '2009-01-01', 'earliest_year': None},
                {'work_id': 300, 'earliest_date': '2025-05-05', 'earliest_year': None},
                {'work_id': 400, 'earliest_date': '2012-01-01', 'earliest_year': None},
                {'work_id': 500, 'earliest_date': '2010-01-01', 'earliest_year': None},
                {'work_id': 600, 'earliest_date': None, 'earliest_year': 2008},
            ],
        ),
        ('GROUP BY t.id', None, [{'track_id': 2, 'earliest_date': '2005-01-01', 'earliest_year': None}]),
        ('AS dated', None, []),
        ('FROM feeds_profile_exclusions', None, list(exclusions)),
    ]


class BuildOldHitsTest(unittest.TestCase):
    def test_each_tier_contributes_and_the_exclusions_hold(self):
        cursor = ScriptedCursor(_rules())
        feed = build_old_hits(_Conn(cursor), 'user', NOW, OldHitsConfig(size=10))
        self.assertEqual(feed.state, 'ok')
        self.assertEqual(feed.title, 'Oude hitjes')
        reasons = {track['id']: track['reason'] for track in feed.tracks}
        # 1: a rested 5-star; 4: much played, long ago; 6: a Deezer hit by a liked artist.
        # Not 2 (rated 1), not 3 (released 2025), not 5 (played ten days ago).
        self.assertEqual(reasons, {1: 'favourite:5', 4: 'worn:8', 6: 'hit:deezer:1'})
        self.assertEqual(feed.tracks[0]['genres'], [])
        self.assertEqual(
            {track['bucket'] for track in feed.tracks}, {'old-hits:favourites', 'old-hits:worn', 'old-hits:hits'}
        )
        self.assertEqual(feed.funnel['emitted'], 3)
        # Every query is bound to the listener where it reads their data.
        ratings = cursor.statements_matching('FROM rating_tracks r')
        self.assertEqual(ratings[0][1], ['user'])
        # Tier 3 only looks at artists the listener likes (10 and 30, never 20 who is rated 1).
        popular = cursor.statements_matching('FROM artist_popular_tracks p')
        self.assertEqual(sorted(popular[0][1]), [10, 30])

    def test_a_profile_exclusion_removes_the_track(self):
        cursor = ScriptedCursor(_rules(exclusions=[{'entity_type': 'label', 'entity_name': 'scantraxx'}]))
        feed = build_old_hits(_Conn(cursor), 'user', NOW, OldHitsConfig(size=10))
        self.assertNotIn(6, [track['id'] for track in feed.tracks])

    def test_a_genre_exclusion_removes_the_track(self):
        cursor = ScriptedCursor(_rules(exclusions=[{'entity_type': 'genre', 'entity_name': 'terror'}]))
        feed = build_old_hits(_Conn(cursor), 'user', NOW, OldHitsConfig(size=10))
        self.assertNotIn(4, [track['id'] for track in feed.tracks])

    def test_a_listener_with_no_ratings_or_listens_has_not_enough_data(self):
        feed = build_old_hits(_Conn(ScriptedCursor([])), 'nobody', NOW, OldHitsConfig())
        self.assertEqual(feed.state, 'not_enough_data')
        self.assertEqual(feed.tracks, [])

    def test_the_same_day_gives_the_same_list(self):
        first = build_old_hits(_Conn(ScriptedCursor(_rules())), 'user', NOW, OldHitsConfig(size=10))
        again = build_old_hits(
            _Conn(ScriptedCursor(_rules())), 'user', NOW + timedelta(hours=3), OldHitsConfig(size=10)
        )
        self.assertEqual([t['id'] for t in first.tracks], [t['id'] for t in again.tracks])


class RouterDispatchTest(unittest.TestCase):
    def test_the_feed_body_is_built_by_the_old_hits_builder(self):
        cursor = ScriptedCursor(_rules())
        with patch.object(feeds_router, 'build_feed', side_effect=AssertionError('not the ranker')):
            body = feeds_router.feed_body(
                _Conn(cursor), 'user', feeds_router._sized(feeds_router._policy('old-hits')), NOW
            )
        self.assertEqual(body['slug'], 'old-hits')
        self.assertEqual(body['state'], 'ok')
        self.assertEqual({track['id'] for track in body['tracks']}, {1, 4, 6})
        self.assertIn('library_path', body['tracks'][0])
        self.assertIn('exhausted', body)

    def test_the_listing_names_it_without_a_profile(self):
        body = feeds_router.list_body(None, None, NOW)
        entry = next(feed for feed in body['feeds'] if feed['slug'] == 'old-hits')
        self.assertEqual(entry['title'], 'Oude hitjes')
        self.assertEqual(entry['subtitle'], 'Oude favorieten die je minder draait')

    def test_its_snapshot_key_moves_with_its_own_settings_only(self):
        values = {}

        def fake_get(key, default=None):
            return values.get(key, default)

        conn = _Conn(ScriptedCursor([]))
        with patch.object(feeds_router.settings, 'get', side_effect=fake_get):
            before_old = feeds_router.params_key(conn, 'user', 'old-hits')
            before_mix = feeds_router.params_key(conn, 'user', 'daily-mix')
            values['old_hits_rest_days'] = 30
            self.assertNotEqual(feeds_router.params_key(conn, 'user', 'old-hits'), before_old)
            self.assertEqual(feeds_router.params_key(conn, 'user', 'daily-mix'), before_mix)

    def test_it_is_kept_warm_by_the_refresh_thread(self):
        self.assertIn('old-hits', feeds_router.SNAPSHOT_SLUGS)


if __name__ == '__main__':
    unittest.main()
