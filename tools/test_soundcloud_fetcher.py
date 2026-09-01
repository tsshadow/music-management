"""Tests for the SoundCloud genre fetcher's failure handling.

The fetcher walks the whole archive one track at a time and pauses after every
yt-dlp call, so how it treats a failure decides how long a pass takes. A track
that SoundCloud will never hand over (deleted, DRM) must not cost the same
minute as a successful fetch, and a source that is actively refusing us must
stop the pass instead of being hammered for the rest of the archive.
"""

import os
import tempfile
import unittest

from tools.soundcloud_fetcher import (
    MAX_CONSECUTIVE_RATE_LIMITS,
    PERMANENT,
    PERMANENT_PAUSE,
    RATE_LIMIT_PAUSE,
    RATE_LIMIT_PAUSE_CAP,
    RATE_LIMITED,
    SUCCESS_PAUSE,
    TRANSIENT,
    FetchResult,
    classify_failure,
    pause_for,
    process_tracks,
)


class FakeSong:
    """Stands in for SoundcloudSong: records what the fetcher wrote."""

    def __init__(self, path, metadata, existing=()):
        self.path = path
        self.metadata = metadata
        self.existing = list(existing)
        self.parsed = False
        self.saved = False

    def rules_genres(self):
        return self.existing

    def parse(self):
        self.parsed = True

    def save_file(self):
        self.saved = True


class FakeGenreHelper:
    """A `rules_genres` helper with a fixed, case-insensitive answer set."""

    def __init__(self, table):
        self.table = {key.lower(): value for key, value in table.items()}

    def get_corrected_or_exists(self, key):
        return self.table.get(key.strip().lower(), False)


def a_file():
    descriptor, path = tempfile.mkstemp(suffix='.mp3')
    os.close(descriptor)
    return path


class ClassifyFailureTest(unittest.TestCase):
    def test_drm_is_permanent(self):
        stderr = (
            'WARNING: [soundcloud] 2099782920: hls_mp3 format not found\n'
            'ERROR: [soundcloud] 2099782920: This video is DRM protected'
        )
        self.assertEqual(classify_failure(stderr), PERMANENT)

    def test_missing_track_is_permanent(self):
        stderr = (
            'ERROR: [soundcloud] wonderlandfestival/ketting: Unable to download JSON '
            'metadata: HTTP Error 404: Not Found'
        )
        self.assertEqual(classify_failure(stderr), PERMANENT)

    def test_forbidden_is_rate_limited(self):
        self.assertEqual(
            classify_failure('ERROR: unable to download video data: HTTP Error 403: Forbidden'), RATE_LIMITED
        )

    def test_too_many_requests_is_rate_limited(self):
        self.assertEqual(classify_failure('ERROR: HTTP Error 429: Too Many Requests'), RATE_LIMITED)

    def test_anything_else_is_transient(self):
        self.assertEqual(classify_failure('ERROR: unable to connect: timed out'), TRANSIENT)


class PauseForTest(unittest.TestCase):
    def test_a_successful_fetch_keeps_the_full_pause(self):
        self.assertEqual(pause_for(None), SUCCESS_PAUSE)

    def test_a_dead_track_is_not_worth_a_minute(self):
        self.assertEqual(pause_for(PERMANENT), PERMANENT_PAUSE)
        self.assertLess(pause_for(PERMANENT), pause_for(None))

    def test_rate_limits_back_off_exponentially(self):
        self.assertEqual(pause_for(RATE_LIMITED, 1), RATE_LIMIT_PAUSE)
        self.assertEqual(pause_for(RATE_LIMITED, 2), RATE_LIMIT_PAUSE * 2)

    def test_the_backoff_is_capped(self):
        self.assertEqual(pause_for(RATE_LIMITED, 99), RATE_LIMIT_PAUSE_CAP)


class ProcessTracksTest(unittest.TestCase):
    def setUp(self):
        self.slept = []
        self.fetched = []
        self.helper = FakeGenreHelper({'uptempo': 'uptempo', 'uptempo hardcore': 'Uptempo Hardcore'})
        self.songs = []

    def song_factory(self, path, metadata):
        song = FakeSong(path, metadata)
        self.songs.append(song)
        return song

    def run_tracks(self, tracks, results):
        def fetch(url):
            self.fetched.append(url)
            return results.pop(0)

        return process_tracks(tracks, self.helper, fetch=fetch, sleep=self.slept.append, song_factory=self.song_factory)

    def test_a_missing_file_is_never_fetched(self):
        counts = self.run_tracks([(1, 'https://soundcloud.com/a/b', '/does/not/exist.mp3')], [])
        self.assertEqual(self.fetched, [])
        self.assertEqual(self.slept, [])
        self.assertEqual(counts.not_found, 1)

    def test_a_permanent_failure_costs_the_short_pause(self):
        counts = self.run_tracks([(1, 'https://soundcloud.com/a/b', a_file())], [FetchResult(None, PERMANENT)])
        self.assertEqual(self.slept, [PERMANENT_PAUSE])
        self.assertEqual(counts.permanent, 1)

    def test_repeated_rate_limits_end_the_pass(self):
        tracks = [
            (index, f'https://soundcloud.com/a/{index}', a_file()) for index in range(MAX_CONSECUTIVE_RATE_LIMITS + 3)
        ]
        results = [FetchResult(None, RATE_LIMITED) for _ in tracks]
        counts = self.run_tracks(tracks, results)
        self.assertEqual(len(self.fetched), MAX_CONSECUTIVE_RATE_LIMITS)
        self.assertTrue(counts.aborted)

    def test_a_success_clears_the_rate_limit_streak(self):
        tracks = [(index, f'https://soundcloud.com/a/{index}', a_file()) for index in range(4)]
        results = [
            FetchResult(None, RATE_LIMITED),
            FetchResult({'genre': 'Uptempo'}, None),
            FetchResult(None, RATE_LIMITED),
            FetchResult(None, RATE_LIMITED),
        ]
        self.run_tracks(tracks, results)
        self.assertEqual(len(self.fetched), 4)
        self.assertEqual(self.slept[2], RATE_LIMIT_PAUSE)

    def test_a_genre_in_another_casing_is_written_in_its_stored_spelling(self):
        counts = self.run_tracks(
            [(1, 'https://soundcloud.com/a/b', a_file())], [FetchResult({'genre': 'UPTEMPO HARDCORE'}, None)]
        )
        self.assertEqual(self.songs[0].metadata['genre'], 'Uptempo Hardcore')
        self.assertTrue(self.songs[0].saved)
        self.assertEqual(counts.updated, 1)

    def test_a_hashtag_genre_is_still_normalized(self):
        self.run_tracks([(1, 'https://soundcloud.com/a/b', a_file())], [FetchResult({'genre': '#uptempo'}, None)])
        self.assertEqual(self.songs[0].metadata['genre'], 'uptempo')

    def test_an_unknown_genre_is_skipped(self):
        counts = self.run_tracks(
            [(1, 'https://soundcloud.com/a/b', a_file())], [FetchResult({'genre': 'rawstyle'}, None)]
        )
        self.assertEqual(self.songs, [])
        self.assertEqual(counts.skipped, 1)
        self.assertEqual(self.slept, [SUCCESS_PAUSE])

    def tearDown(self):
        for song in self.songs:
            if os.path.exists(song.path):
                os.unlink(song.path)
