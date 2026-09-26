import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.music_manager.artist_image_fetcher import fetcher as fetcher_module
from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher
from services.music_manager.artist_image_fetcher.providers.base import ProviderRateLimited, ProviderUnavailable
from services.music_manager.tests.scripted_cursor import assert_atomic, assert_rolled_back, transaction_log


def make_cursor(conn):
    """pymysql cursors are used as context managers; hand back the same mock either way."""
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    return cursor


class FetcherTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(
            os.environ,
            {'ARTIST_IMAGE_STORAGE_PATH': self.tmp.name, 'ARTIST_IMAGE_PUBLIC_BASE_URL': '/media/artist-images'},
        )
        env.start()
        self.addCleanup(env.stop)
        self.conn = MagicMock()
        self.cursor = make_cursor(self.conn)
        self.fetcher = ArtistImageFetcher(db_conn=self.conn)
        self.fetcher.mb_provider = MagicMock()
        self.fetcher.mb_provider.get_artist_metadata.return_value = None
        self.fetcher.providers = []
        self.fetcher.downloader = MagicMock()
        self.fetcher.storage = MagicMock()
        self.fetcher.storage.storage_path = self.tmp.name
        self.fetcher.storage.public_base_url = '/media/artist-images'
        self.fetcher.storage.save_image.return_value = {
            'cached_path': os.path.join(self.tmp.name, 'a.jpg'),
            'public_path': '/media/artist-images/1/a.jpg',
            'width': 100,
            'height': 100,
            'mime_type': 'image/jpeg',
            'file_size': 10,
        }

    def add_provider(self, name, candidates, configured=True):
        provider = MagicMock()
        provider.name = name
        provider.configured = configured
        provider.get_artist_images.return_value = candidates
        self.fetcher.providers.append(provider)
        return provider

    def statements(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]

    def assert_status_untouched(self):
        self.assertFalse(any('image_status = %s' in s for s in self.statements()))


class ConstructionTest(unittest.TestCase):
    def test_without_a_connection_one_is_opened_through_the_shared_connector(self):
        with patch.object(fetcher_module, 'DatabaseConnector') as connector:
            instance = ArtistImageFetcher()
        connector.return_value.connect.assert_called_once()
        self.assertEqual(len(instance.providers), 3)
        self.assertEqual([p.name for p in instance.providers], ['spotify', 'soundcloud', 'lastfm'])

    def test_the_storage_location_falls_back_to_the_library_default(self):
        with patch.dict(os.environ, {}, clear=True):
            instance = ArtistImageFetcher(db_conn=MagicMock())
        self.assertEqual(instance.storage.storage_path, '/mnt/music/artists')
        self.assertEqual(instance.storage.public_base_url, '/media/artist-images')


class FetchForArtistTest(FetcherTestCase):
    def test_an_unknown_artist_id_is_reported_as_a_failure(self):
        self.cursor.fetchone.return_value = None
        self.assertFalse(self.fetcher.fetch_for_artist(1))

    def test_an_artist_that_already_has_an_image_is_skipped(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Angerfist', 'mbid': None, 'primary_image_id': 9}
        self.assertTrue(self.fetcher.fetch_for_artist(1))
        self.fetcher.mb_provider.get_artist_metadata.assert_not_called()

    # These three need a sighted fetcher: a blind one stops before the MusicBrainz step.
    def test_force_refresh_processes_an_artist_that_already_has_an_image(self):
        self.add_provider('spotify', [])
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Angerfist', 'mbid': None, 'primary_image_id': 9}
        self.cursor.fetchall.return_value = []
        self.assertFalse(self.fetcher.fetch_for_artist(1, force_refresh=True))
        self.fetcher.mb_provider.get_artist_metadata.assert_called_once()

    def test_a_supplied_name_skips_the_name_lookup_but_still_reads_the_mbid(self):
        self.add_provider('spotify', [])
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': 'mb1', 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.fetcher.fetch_for_artist(1, 'Angerfist')
        self.fetcher.mb_provider.get_artist_metadata.assert_called_once_with('Angerfist', 'mb1')

    def test_an_artist_row_that_is_gone_leaves_the_mbid_empty(self):
        self.add_provider('spotify', [])
        self.cursor.fetchone.return_value = None
        self.cursor.fetchall.return_value = []
        self.fetcher.fetch_for_artist(1, 'Angerfist')
        self.fetcher.mb_provider.get_artist_metadata.assert_called_once_with('Angerfist', None)

    def test_musicbrainz_metadata_backfills_the_mbid_and_the_external_ids(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.fetcher.mb_provider.get_artist_metadata.return_value = {
            'mbid': 'mb-new',
            'name': 'Angerfist',
            'external_ids': {'spotify': 'sp1'},
        }
        provider = self.add_provider('spotify', [])
        self.fetcher.fetch_for_artist(1, 'Angerfist')
        self.assertEqual(provider.get_artist_images.call_args.args[1], 'mb-new')
        self.assertEqual(provider.get_artist_images.call_args.args[2], {'spotify': 'sp1'})
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertTrue(any('UPDATE library_artists SET mbid' in s for s in statements))
        self.assertTrue(any('INSERT INTO artist_external_ids' in s for s in statements))

    def test_an_external_id_that_is_already_stored_is_not_written_again(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': 'mb1', 'primary_image_id': None}
        self.cursor.fetchall.return_value = [{'source': 'spotify', 'external_id': 'sp-existing'}]
        self.fetcher.mb_provider.get_artist_metadata.return_value = {
            'mbid': 'mb1',
            'name': 'Angerfist',
            'external_ids': {'spotify': 'sp-other'},
        }
        self.add_provider('spotify', [])
        self.fetcher.fetch_for_artist(1, 'Angerfist')
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertFalse(any('INSERT INTO artist_external_ids' in s for s in statements))

    def test_a_provider_that_raises_does_not_stop_the_others(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        broken = self.add_provider('spotify', [])
        broken.get_artist_images.side_effect = RuntimeError('api down')
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))

    def test_without_a_confident_candidate_the_artist_is_marked_as_failed(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Someone Else', 'url': 'https://img.test/a.jpg'}]
        )
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        self.assertTrue(any('image_status = %s' in s for s in self.statements()))

    # The August 2026 blindness: every provider unconfigured, 45.000 artists written down
    # as unfindable. A fetcher with nobody to ask records nothing and says so.
    def test_without_any_configured_provider_nothing_is_looked_up_and_nothing_is_recorded(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        spotify = self.add_provider('spotify', [], configured=False)
        self.assertTrue(self.fetcher.blind)
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Sefa'))
        spotify.get_artist_images.assert_not_called()
        self.fetcher.mb_provider.get_artist_metadata.assert_not_called()
        self.assert_status_untouched()

    def test_the_soundcloud_stub_alone_does_not_make_a_run_sighted(self):
        self.add_provider('soundcloud', [])
        self.assertTrue(self.fetcher.blind)
        self.add_provider('spotify', [])
        self.assertFalse(self.fetcher.blind)

    def test_an_unconfigured_provider_is_not_asked(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        lastfm = self.add_provider('lastfm', [], configured=False)
        self.add_provider(
            'spotify', [{'source': 'spotify', 'source_id': 's1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        lastfm.get_artist_images.assert_not_called()

    # A provider that could not answer -- rate limit, rejected credential, network -- is not
    # a verdict about the artist. The status stays and the next run asks again.
    def test_a_provider_that_could_not_answer_defers_the_artist_instead_of_failing_it(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        spotify = self.add_provider('spotify', [])
        spotify.get_artist_images.side_effect = ProviderUnavailable('Spotify: lookup answered 429')
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Sefa'))
        self.assert_status_untouched()

    def test_a_provider_that_blew_up_defers_the_artist_too(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        spotify = self.add_provider('spotify', [])
        spotify.get_artist_images.side_effect = RuntimeError('api down')
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Sefa'))
        self.assert_status_untouched()

    def test_a_confident_hit_from_one_provider_wins_even_when_another_could_not_answer(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        spotify = self.add_provider('spotify', [])
        spotify.get_artist_images.side_effect = ProviderUnavailable('Spotify: lookup answered 429')
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))

    def test_the_most_confident_candidate_wins(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm',
            [
                {'source': 'lastfm', 'source_id': 'weak', 'name': 'Angerfst', 'url': 'https://img.test/weak.jpg'},
                {'source': 'lastfm', 'source_id': 'strong', 'name': 'Angerfist', 'url': 'https://img.test/strong.jpg'},
            ],
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        self.fetcher.downloader.download.assert_called_once_with('https://img.test/strong.jpg')

    def test_a_candidate_that_already_carries_its_bytes_is_not_downloaded_again(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm',
            [
                {
                    'source': 'lastfm',
                    'source_id': 'l1',
                    'name': 'Angerfist',
                    'url': 'https://img.test/a.jpg',
                    'image_data': b'inline',
                }
            ],
        )
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        self.fetcher.downloader.download.assert_not_called()
        self.assertEqual(self.fetcher.storage.save_image.call_args.args[2], b'inline')

    # A provider found the artist; the CDN, the disk or the database failed. That says
    # nothing about the artist, and `failed` would hide it for 30 days.
    def test_a_download_that_yields_nothing_defers_the_artist_without_a_verdict(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = None
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        self.assert_status_untouched()

    def test_a_download_that_raises_defers_the_artist_without_a_verdict(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.side_effect = RuntimeError('503 from the CDN')
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        self.assert_status_untouched()

    def test_a_storage_error_defers_the_artist_without_a_verdict(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.fetcher.storage.save_image.side_effect = RuntimeError('disk full')
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        self.assert_status_untouched()

    # Clearing a portrait is a curation decision; the start-up bulk run used to undo it.
    def test_an_artist_whose_portrait_was_cleared_is_not_looked_up(self):
        self.cursor.fetchone.return_value = {
            'id': 1,
            'name': 'Angerfist',
            'mbid': None,
            'primary_image_id': None,
            'image_status': 'cleared',
        }
        spotify = self.add_provider('spotify', [])
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Angerfist', force_refresh=True))
        spotify.get_artist_images.assert_not_called()
        self.fetcher.mb_provider.get_artist_metadata.assert_not_called()
        self.assert_status_untouched()

    def test_a_cleared_portrait_is_looked_up_when_explicitly_overridden(self):
        self.cursor.fetchone.return_value = {
            'id': 1,
            'name': 'Angerfist',
            'mbid': None,
            'primary_image_id': None,
            'image_status': 'cleared',
        }
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'spotify', [{'source': 'spotify', 'source_id': 's1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist', force_refresh=True, override_cleared=True))

    def test_a_successful_fetch_records_the_image_and_promotes_it_to_primary(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.cursor.lastrowid = 55
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertTrue(any('INSERT INTO library_artist_images' in s for s in statements))
        self.assertTrue(any('is_primary = 1' in s for s in statements))
        self.assertTrue(any("image_status = 'active'" in s for s in statements))


class RunTestCase(FetcherTestCase):
    """A bulk run with one configured provider, its log captured from INFO upward."""

    HIT = [{'source': 'spotify', 'source_id': 's1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]

    def setUp(self):
        super().setUp()
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.fetcher.stop_event = MagicMock()
        self.fetcher.stop_event.wait.return_value = False
        self.fetcher.downloader.download.return_value = b'binary'
        self.spotify = self.add_provider('spotify', [])

    def records(self, level):
        return [r for r in self.logs.records if r.levelname == level]

    def fetch(self, *names):
        with self.assertLogs(fetcher_module.__name__, level='INFO') as self.logs:
            results = [self.fetcher.fetch_for_artist(1, name) for name in names]
            self.fetcher.log_run_summary()
        return results


class RateLimitTest(RunTestCase):
    """On 2026-09-24 a 429 on ~40% of lookups produced 3.278 WARNINGs and a push every
    five minutes: the fetcher walked on to the next artist instead of waiting."""

    def test_a_rate_limit_pauses_for_retry_after_and_retries_the_same_artist(self):
        self.spotify.get_artist_images.side_effect = [ProviderRateLimited('429', 17.0), self.HIT]
        self.assertEqual(self.fetch('Angerfist'), [True])
        self.fetcher.stop_event.wait.assert_called_once_with(17.0)
        self.assertEqual([c.args[0] for c in self.spotify.get_artist_images.call_args_list], ['Angerfist', 'Angerfist'])

    def test_still_limited_after_the_pause_defers_the_artist(self):
        self.spotify.get_artist_images.side_effect = ProviderRateLimited('429', 5.0)
        self.assertEqual(self.fetch('Sefa'), [False])
        self.assertEqual(self.spotify.get_artist_images.call_count, 2)
        self.fetcher.stop_event.wait.assert_called_once_with(5.0)
        self.assert_status_untouched()
        self.assertEqual(self.fetcher.run_stats['deferred'], 1)

    def test_a_stop_during_the_pause_defers_without_retrying(self):
        self.fetcher.stop_event.wait.return_value = True
        self.spotify.get_artist_images.side_effect = [ProviderRateLimited('429', 5.0), self.HIT]
        self.assertEqual(self.fetch('Sefa'), [False])
        self.assertEqual(self.spotify.get_artist_images.call_count, 1)
        self.assert_status_untouched()

    def test_per_artist_failures_are_info_and_the_run_gets_one_summary_warning(self):
        self.spotify.get_artist_images.side_effect = [
            ProviderUnavailable('Spotify: lookup answered 502'),
            ProviderUnavailable('Spotify: lookup failed: connection reset'),
            ProviderUnavailable('Spotify: lookup answered 503'),
        ]
        self.fetch('A', 'B', 'C')
        warnings = self.records('WARNING')
        self.assertEqual(len(warnings), 1)
        self.assertIn('3 artist(s) deferred', warnings[0].getMessage())
        self.assertEqual(len([r for r in self.records('INFO') if 'could not answer for' in r.getMessage()]), 3)

    def test_only_the_first_rate_limit_of_a_run_is_a_warning(self):
        self.spotify.get_artist_images.side_effect = [
            ProviderRateLimited('429', 10.0),
            [],
            ProviderRateLimited('429', 20.0),
            [],
            ProviderRateLimited('429', 30.0),
            [],
        ]
        self.fetch('A', 'B', 'C')
        warnings = [r.getMessage() for r in self.records('WARNING')]
        self.assertEqual(len(warnings), 2)
        self.assertIn('pausing 10s', warnings[0])
        self.assertIn('3 rate-limit pause(s), 60s paused in total', warnings[1])
        self.assertEqual(self.fetcher.run_stats['rate_limit_pauses'], 3)

    def test_a_clean_run_summary_is_info(self):
        self.spotify.get_artist_images.return_value = self.HIT
        self.fetch('Angerfist')
        self.assertEqual(self.records('WARNING'), [])
        self.assertTrue(any('0 artist(s) deferred' in r.getMessage() for r in self.records('INFO')))

    def test_start_run_resets_the_counters_and_the_first_warning(self):
        self.spotify.get_artist_images.side_effect = [ProviderRateLimited('429', 10.0), []]
        self.fetch('A')
        self.fetcher.start_run()
        self.assertEqual(
            self.fetcher.run_stats,
            {
                'deferred': 0,
                'rate_limit_pauses': 0,
                'pause_seconds': 0.0,
                'provider_failures': {},
                'download_failures': 0,
            },
        )
        self.spotify.get_artist_images.side_effect = [ProviderRateLimited('429', 10.0), []]
        self.fetch('B')
        self.assertTrue(any('pausing 10s' in r.getMessage() for r in self.records('WARNING')))

    def test_by_default_the_pause_waits_on_a_real_event(self):
        instance = ArtistImageFetcher(db_conn=MagicMock())
        with patch.object(instance.stop_event, 'wait', return_value=False) as wait:
            self.assertTrue(instance._pause_for_rate_limit('spotify', 'A', 3.0))
        wait.assert_called_once_with(3.0)


class QuietFailureTest(RunTestCase):
    """MusicBrainz and the image download used to log a WARNING or an ERROR per artist,
    each a push on the phone; they are INFO now, counted into the one run summary."""

    def setUp(self):
        super().setUp()
        self.spotify.get_artist_images.return_value = self.HIT

    def test_a_musicbrainz_timeout_is_info_and_counted_per_provider(self):
        self.fetcher.mb_provider.get_artist_metadata.side_effect = ProviderUnavailable('MusicBrainz: timed out')
        self.assertEqual(self.fetch('Angerfist', 'Angerfist'), [True, True])
        self.assertEqual(self.records('WARNING'), [])
        self.assertEqual(len([r for r in self.records('INFO') if 'MusicBrainz could not answer' in r.getMessage()]), 2)
        self.assertEqual(self.fetcher.run_stats['provider_failures'], {'musicbrainz': 2})
        self.assertTrue(any('provider non-answers: musicbrainz 2' in r.getMessage() for r in self.records('INFO')))

    def test_a_musicbrainz_rate_limit_pauses_the_run_and_asks_again(self):
        metadata = {'mbid': 'mb1', 'name': 'Angerfist', 'external_ids': {}}
        self.fetcher.mb_provider.get_artist_metadata.side_effect = [ProviderRateLimited('503', 12.0), metadata]
        self.fetch('Angerfist')
        self.fetcher.stop_event.wait.assert_called_once_with(12.0)
        self.assertEqual(self.fetcher.mb_provider.get_artist_metadata.call_count, 2)
        self.assertEqual(self.fetcher.run_stats['provider_failures'], {})
        self.assertEqual(self.fetcher.run_stats['rate_limit_pauses'], 1)

    def test_a_musicbrainz_still_limited_after_the_pause_is_counted_and_the_lookup_goes_on(self):
        self.fetcher.mb_provider.get_artist_metadata.side_effect = ProviderRateLimited('429', 5.0)
        self.assertEqual(self.fetch('Angerfist'), [True])
        self.assertEqual(self.fetcher.run_stats['provider_failures'], {'musicbrainz': 1})

    def test_other_provider_non_answers_are_counted_per_provider(self):
        self.spotify.get_artist_images.side_effect = [ProviderUnavailable('502'), RuntimeError('bug')]
        self.fetch('Angerfist', 'Angerfist')
        self.assertEqual(self.fetcher.run_stats['provider_failures'], {'spotify': 2})
        self.assertEqual(self.records('ERROR'), [])

    def test_a_failed_download_is_info_and_the_summary_reports_it(self):
        self.fetcher.downloader.download.side_effect = RuntimeError('503 from the CDN')
        self.assertEqual(self.fetch('Angerfist', 'Angerfist', 'Angerfist'), [False, False, False])
        self.assertEqual(self.records('ERROR'), [])
        warnings = [r.getMessage() for r in self.records('WARNING')]
        self.assertEqual(len(warnings), 1)
        self.assertIn('3 image download(s) failed', warnings[0])
        self.assertEqual(self.fetcher.run_stats['download_failures'], 3)
        self.assert_status_untouched()

    def test_an_unwritable_image_directory_is_one_error_per_run(self):
        self.fetcher.storage.save_image.side_effect = PermissionError(13, 'Permission denied', '/mnt/music/artists/1')
        self.fetch('Angerfist', 'Angerfist', 'Angerfist')
        errors = [r.getMessage() for r in self.records('ERROR')]
        self.assertEqual(len(errors), 1)
        self.assertIn('cannot be written', errors[0])
        self.assertEqual(self.fetcher.run_stats['download_failures'], 3)
        self.fetcher.start_run()
        self.fetch('Angerfist')
        self.assertEqual(len(self.records('ERROR')), 1)

    def test_a_blind_fetcher_logs_each_skipped_artist_at_info(self):
        self.fetcher.providers = []
        self.fetch('Angerfist', 'Angerfist')
        self.assertEqual(self.records('WARNING'), [])

    def test_the_summary_returns_every_counter(self):
        self.fetcher.downloader.download.side_effect = RuntimeError('boom')
        self.fetcher.mb_provider.get_artist_metadata.side_effect = ProviderUnavailable('timed out')
        self.fetch('Angerfist')
        stats = self.fetcher.log_run_summary()
        self.assertEqual(stats['download_failures'], 1)
        self.assertEqual(stats['provider_failures'], {'musicbrainz': 1})
        stats['provider_failures']['spotify'] = 9
        self.assertNotIn('spotify', self.fetcher.run_stats['provider_failures'])


class ManifestTest(FetcherTestCase):
    # manifest.json was read and rewritten whole for every artist (quadratic on the CIFS
    # share, racing between runs) and nothing ever read it.
    def test_a_successful_fetch_no_longer_writes_a_manifest(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, 'manifest.json')))


class SetPrimaryImageAtomicityTest(FetcherTestCase):
    """The fetcher's primary flags and the artist's pointer land together (bug report 115)."""

    def test_the_three_updates_are_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        self.fetcher._set_primary_image(1, 9)
        assert_atomic(self, log, 'is_primary = 0', 'is_primary = 1', 'SET primary_image_id = %s')

    def test_a_failing_pointer_update_rolls_the_flags_back(self):
        """On the CLI's plain connection the flags otherwise waited for the next artist's commit."""
        log = transaction_log(self.conn, self.cursor, fail_on='SET primary_image_id = %s')
        with self.assertRaises(RuntimeError):
            self.fetcher._set_primary_image(1, 9)
        assert_rolled_back(self, log)


if __name__ == '__main__':
    unittest.main()
