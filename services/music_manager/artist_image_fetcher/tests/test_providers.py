import unittest
from unittest.mock import MagicMock, patch

from requests.exceptions import Timeout

from services.music_manager.artist_image_fetcher.providers import lastfm, musicbrainz, soundcloud, spotify
from services.music_manager.artist_image_fetcher.providers.base import ProviderUnavailable


def make_response(status_code=200, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload if payload is not None else {}
    return response


class LastFmProviderTest(unittest.TestCase):
    def setUp(self):
        self.provider = lastfm.LastFmArtistImageProvider(api_key='key')

    def test_the_provider_is_named_after_its_source(self):
        self.assertEqual(self.provider.name, 'lastfm')

    # A provider without its key is not configured, and asking it anyway is "could
    # not answer" -- never the empty list that means "looked, found nothing".
    def test_without_an_api_key_the_provider_is_not_configured(self):
        with patch.dict('os.environ', {}, clear=True), patch.object(lastfm, 'credential', return_value=None):
            provider = lastfm.LastFmArtistImageProvider()
        self.assertFalse(provider.configured)
        with patch.object(lastfm, 'requests') as http:
            with self.assertRaises(ProviderUnavailable):
                provider.get_artist_images('Angerfist')
        http.get.assert_not_called()

    def test_the_key_comes_from_the_config_store_before_the_environment(self):
        with patch.object(lastfm, 'credential', return_value='stored') as cred:
            provider = lastfm.LastFmArtistImageProvider()
        cred.assert_called_once_with('lastfm_api_key', 'LASTFM_API_KEY')
        self.assertEqual(provider.api_key, 'stored')
        self.assertTrue(provider.configured)

    def test_only_the_largest_images_become_candidates(self):
        payload = {
            'artist': {
                'name': 'Angerfist',
                'mbid': 'mb-1',
                'image': [
                    {'size': 'small', '#text': 'https://img.test/small.jpg'},
                    {'size': 'extralarge', '#text': 'https://img.test/xl.jpg'},
                    {'size': 'mega', '#text': 'https://img.test/mega.jpg'},
                    {'size': 'mega', '#text': ''},
                ],
                'stats': {'listeners': '10', 'playcount': '20'},
                'bio': {'summary': 'bio text'},
            }
        }
        with patch.object(lastfm, 'requests') as http:
            http.get.return_value = make_response(payload=payload)
            candidates = self.provider.get_artist_images('Angerfist', mbid='mb-1')
        self.assertEqual([c['url'] for c in candidates], ['https://img.test/xl.jpg', 'https://img.test/mega.jpg'])
        self.assertTrue(all(c['source'] == 'lastfm' for c in candidates))
        self.assertTrue(candidates[0]['is_known_match'])
        self.assertEqual(candidates[0]['metadata']['listeners'], '10')

    def test_a_non_200_response_is_the_provider_not_answering(self):
        with patch.object(lastfm, 'requests') as http:
            http.get.return_value = make_response(status_code=503)
            with self.assertRaises(ProviderUnavailable):
                self.provider.get_artist_images('Angerfist')

    def test_a_transport_error_is_the_provider_not_answering(self):
        with patch.object(lastfm, 'requests') as http:
            http.get.side_effect = RuntimeError('network down')
            with self.assertRaises(ProviderUnavailable):
                self.provider.get_artist_images('Angerfist')

    def test_a_200_without_images_is_a_real_empty_answer(self):
        with patch.object(lastfm, 'requests') as http:
            http.get.return_value = make_response(
                payload={'error': 6, 'message': 'The artist you supplied could not be found'}
            )
            self.assertEqual(self.provider.get_artist_images('Nobody'), [])


class SpotifyProviderTest(unittest.TestCase):
    def setUp(self):
        self.provider = spotify.SpotifyArtistImageProvider(client_id='id', client_secret='secret')

    def test_the_provider_is_named_after_its_source(self):
        self.assertEqual(self.provider.name, 'spotify')

    def test_without_credentials_the_provider_is_not_configured_and_never_answers_empty(self):
        with patch.dict('os.environ', {}, clear=True), patch.object(spotify, 'credential', return_value=None):
            provider = spotify.SpotifyArtistImageProvider()
        self.assertFalse(provider.configured)
        with patch.object(spotify, 'requests') as http:
            with self.assertRaises(ProviderUnavailable):
                provider.get_artist_images('Angerfist')
        http.post.assert_not_called()

    def test_the_credentials_come_from_the_config_store_before_the_environment(self):
        with patch.object(spotify, 'credential', side_effect=['stored-id', 'stored-secret']) as cred:
            provider = spotify.SpotifyArtistImageProvider()
        self.assertEqual(
            [c.args for c in cred.call_args_list],
            [('spotify_client_id', 'SPOTIFY_CLIENT_ID'), ('spotify_client_secret', 'SPOTIFY_CLIENT_SECRET')],
        )
        self.assertEqual((provider.client_id, provider.client_secret), ('stored-id', 'stored-secret'))

    def test_the_token_is_fetched_once_and_then_reused(self):
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            self.assertEqual(self.provider._get_token(), 'tok')
            self.assertEqual(self.provider._get_token(), 'tok')
        self.assertEqual(http.post.call_count, 1)

    # A credential Spotify rejects is a broken configuration, which looks exactly like
    # "no image exists" if it is allowed to answer with an empty list.
    def test_a_rejected_token_request_is_the_provider_not_answering(self):
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(status_code=401)
            with self.assertRaises(ProviderUnavailable):
                self.provider.get_artist_images('Angerfist')
        http.get.assert_not_called()

    def test_a_token_request_that_raises_is_the_provider_not_answering(self):
        with patch.object(spotify, 'requests') as http:
            http.post.side_effect = RuntimeError('network down')
            with self.assertRaises(ProviderUnavailable):
                self.provider._get_token()

    def test_a_search_turns_every_image_of_every_hit_into_a_candidate(self):
        payload = {
            'artists': {
                'items': [
                    {
                        'id': 'sp1',
                        'name': 'Angerfist',
                        'popularity': 60,
                        'genres': ['hardcore'],
                        'followers': {'total': 1000},
                        'images': [
                            {'url': 'https://img.test/a.jpg', 'width': 640, 'height': 640},
                            {'url': 'https://img.test/b.jpg', 'width': 320, 'height': 320},
                        ],
                    },
                ]
            }
        }
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            http.get.return_value = make_response(payload=payload)
            candidates = self.provider.get_artist_images('Angerfist')
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]['source_id'], 'sp1')
        self.assertFalse(candidates[0]['is_known_match'])
        self.assertEqual(candidates[0]['metadata']['followers'], 1000)
        self.assertEqual(http.get.call_args.args[0], spotify.SpotifyArtistImageProvider.SEARCH_URL)

    def test_a_known_spotify_id_is_looked_up_directly_and_marked_as_a_known_match(self):
        artist = {
            'id': 'sp9',
            'name': 'Angerfist',
            'popularity': 70,
            'genres': [],
            'followers': {'total': 5},
            'images': [{'url': 'https://img.test/x.jpg', 'width': 1, 'height': 1}],
        }
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            http.get.return_value = make_response(payload=artist)
            candidates = self.provider.get_artist_images('Angerfist', external_ids={'spotify': 'sp9'})
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]['is_known_match'])
        self.assertIn('/artists/sp9', http.get.call_args.args[0])

    def test_a_rate_limited_search_is_the_provider_not_answering(self):
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            http.get.return_value = make_response(status_code=429)
            with self.assertRaises(ProviderUnavailable):
                self.provider.get_artist_images('Angerfist')

    def test_a_transport_error_during_search_is_the_provider_not_answering(self):
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            http.get.side_effect = RuntimeError('network down')
            with self.assertRaises(ProviderUnavailable):
                self.provider.get_artist_images('Angerfist')

    def test_a_search_without_hits_is_a_real_empty_answer(self):
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            http.get.return_value = make_response(payload={'artists': {'items': []}})
            self.assertEqual(self.provider.get_artist_images('Nobody'), [])

    def test_a_known_id_spotify_no_longer_has_is_a_real_empty_answer(self):
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            http.get.return_value = make_response(status_code=404)
            self.assertEqual(self.provider.get_artist_images('Gone', external_ids={'spotify': 'sp9'}), [])


class MusicBrainzProviderTest(unittest.TestCase):
    def setUp(self):
        musicbrainz.MusicBrainzArtistProvider._last_call_time = 0
        self.provider = musicbrainz.MusicBrainzArtistProvider()
        patcher = patch.object(musicbrainz.time, 'sleep')
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_provider_is_named_after_its_source(self):
        self.assertEqual(self.provider.name, 'musicbrainz')

    def test_musicbrainz_supplies_metadata_only_never_images(self):
        self.assertEqual(self.provider.get_artist_images('Angerfist'), [])

    def test_two_calls_in_a_row_are_spaced_out(self):
        with patch.object(musicbrainz, 'requests') as http:
            http.get.return_value = make_response(payload={'artists': [{'id': 'mb1', 'name': 'Angerfist'}]})
            self.provider.get_artist_metadata('Angerfist')
            self.provider.get_artist_metadata('Angerfist')
        self.sleep.assert_called()

    def test_a_search_returns_the_first_hit(self):
        with patch.object(musicbrainz, 'requests') as http:
            http.get.return_value = make_response(
                payload={'artists': [{'id': 'mb1', 'name': 'Angerfist'}, {'id': 'mb2'}]}
            )
            metadata = self.provider.get_artist_metadata('Angerfist')
        self.assertEqual(metadata['mbid'], 'mb1')
        self.assertEqual(metadata['name'], 'Angerfist')
        self.assertEqual(http.get.call_args.kwargs['params']['query'], 'artist:Angerfist')

    def test_a_search_without_hits_returns_nothing(self):
        with patch.object(musicbrainz, 'requests') as http:
            http.get.return_value = make_response(payload={'artists': []})
            self.assertIsNone(self.provider.get_artist_metadata('Nobody'))

    def test_a_read_timeout_is_retried_before_giving_up(self):
        # musicbrainz.org routinely takes longer than a couple of seconds to answer.
        # A single-shot 5s timeout turned that into ~2.3k ERROR lines a day in
        # production while the very next attempt would usually have succeeded.
        payload = {'artists': [{'id': 'mb1', 'name': 'Angerfist'}]}
        with patch.object(musicbrainz, 'requests') as http:
            http.get.side_effect = [Timeout('read timed out'), make_response(payload=payload)]
            metadata = self.provider.get_artist_metadata('Angerfist')
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata['mbid'], 'mb1')
        self.assertEqual(http.get.call_count, 2)

    def test_a_persistent_timeout_gives_up_and_returns_nothing(self):
        with patch.object(musicbrainz, 'requests') as http:
            http.get.side_effect = Timeout('read timed out')
            self.assertIsNone(self.provider.get_artist_metadata('Angerfist'))
        self.assertGreater(http.get.call_count, 1)

    def test_the_read_timeout_is_longer_than_the_connect_timeout(self):
        with patch.object(musicbrainz, 'requests') as http:
            http.get.return_value = make_response(payload={'artists': []})
            self.provider.get_artist_metadata('Angerfist')
        connect_timeout, read_timeout = http.get.call_args.kwargs['timeout']
        self.assertGreaterEqual(read_timeout, 15)
        self.assertGreater(read_timeout, connect_timeout)

    def test_a_lookup_by_mbid_uses_the_direct_url_and_reads_the_relations(self):
        payload = {
            'id': 'mb1',
            'name': 'Angerfist',
            'relations': [
                {'target-type': 'url', 'url': {'resource': 'https://open.spotify.com/artist/sp1?si=x'}},
                {'target-type': 'url', 'url': {'resource': 'https://soundcloud.com/angerfist'}},
                {'target-type': 'url', 'url': {'resource': 'https://www.last.fm/music/Angerfist'}},
                {'target-type': 'url', 'url': {'resource': 'https://example.test/other'}},
            ],
        }
        with patch.object(musicbrainz, 'requests') as http:
            http.get.return_value = make_response(payload=payload)
            metadata = self.provider.get_artist_metadata('Angerfist', mbid='mb1')
        self.assertTrue(http.get.call_args.args[0].endswith('/mb1'))
        self.assertEqual(metadata['external_ids'], {'spotify': 'sp1', 'soundcloud': 'angerfist', 'lastfm': 'Angerfist'})

    def test_a_non_200_response_returns_nothing(self):
        with patch.object(musicbrainz, 'requests') as http:
            http.get.return_value = make_response(status_code=503)
            self.assertIsNone(self.provider.get_artist_metadata('Angerfist'))

    def test_a_transport_error_returns_nothing(self):
        with patch.object(musicbrainz, 'requests') as http:
            http.get.side_effect = RuntimeError('network down')
            self.assertIsNone(self.provider.get_artist_metadata('Angerfist'))


class SoundCloudProviderTest(unittest.TestCase):
    def test_the_provider_is_named_after_its_source(self):
        self.assertEqual(soundcloud.SoundCloudArtistImageProvider().name, 'soundcloud')

    def test_without_a_database_connection_nothing_is_looked_up(self):
        provider = soundcloud.SoundCloudArtistImageProvider()
        self.assertEqual(provider.get_artist_images('Angerfist'), [])

    def test_a_known_external_id_skips_the_database_entirely(self):
        conn = MagicMock()
        provider = soundcloud.SoundCloudArtistImageProvider(db_conn=conn)
        self.assertEqual(provider.get_artist_images('Angerfist', external_ids={'soundcloud': 'angerfist'}), [])
        conn.cursor.assert_not_called()

    def test_the_accounts_table_is_queried_with_both_the_plain_and_the_slug_name(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [('downloads_soundcloud_accounts',), ('angerfist', 42)]
        provider = soundcloud.SoundCloudArtistImageProvider(db_conn=conn)
        self.assertEqual(provider.get_artist_images('Anger Fist'), [])
        self.assertEqual(cursor.execute.call_args.args[1], ('Anger Fist', 'anger-fist'))

    def test_a_missing_accounts_table_is_not_queried(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        provider = soundcloud.SoundCloudArtistImageProvider(db_conn=conn)
        self.assertEqual(provider.get_artist_images('Angerfist'), [])
        self.assertEqual(cursor.execute.call_count, 1)

    def test_a_database_error_is_swallowed(self):
        conn = MagicMock()
        conn.cursor.side_effect = RuntimeError('database gone')
        provider = soundcloud.SoundCloudArtistImageProvider(db_conn=conn)
        self.assertEqual(provider.get_artist_images('Angerfist'), [])


if __name__ == '__main__':
    unittest.main()
