import unittest
from unittest.mock import MagicMock, patch

from services.music_manager.artist_image_fetcher.providers import lastfm, musicbrainz, soundcloud, spotify


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

    def test_without_an_api_key_the_provider_is_disabled(self):
        with patch.dict('os.environ', {}, clear=True):
            provider = lastfm.LastFmArtistImageProvider()
        with patch.object(lastfm, 'requests') as http:
            self.assertEqual(provider.get_artist_images('Angerfist'), [])
        http.get.assert_not_called()

    def test_only_the_largest_images_become_candidates(self):
        payload = {'artist': {'name': 'Angerfist', 'mbid': 'mb-1', 'image': [
            {'size': 'small', '#text': 'https://img.test/small.jpg'},
            {'size': 'extralarge', '#text': 'https://img.test/xl.jpg'},
            {'size': 'mega', '#text': 'https://img.test/mega.jpg'},
            {'size': 'mega', '#text': ''},
        ], 'stats': {'listeners': '10', 'playcount': '20'}, 'bio': {'summary': 'bio text'}}}
        with patch.object(lastfm, 'requests') as http:
            http.get.return_value = make_response(payload=payload)
            candidates = self.provider.get_artist_images('Angerfist', mbid='mb-1')
        self.assertEqual([c['url'] for c in candidates], ['https://img.test/xl.jpg', 'https://img.test/mega.jpg'])
        self.assertTrue(all(c['source'] == 'lastfm' for c in candidates))
        self.assertTrue(candidates[0]['is_known_match'])
        self.assertEqual(candidates[0]['metadata']['listeners'], '10')

    def test_a_non_200_response_yields_no_candidates(self):
        with patch.object(lastfm, 'requests') as http:
            http.get.return_value = make_response(status_code=503)
            self.assertEqual(self.provider.get_artist_images('Angerfist'), [])

    def test_a_transport_error_yields_no_candidates(self):
        with patch.object(lastfm, 'requests') as http:
            http.get.side_effect = RuntimeError('network down')
            self.assertEqual(self.provider.get_artist_images('Angerfist'), [])


class SpotifyProviderTest(unittest.TestCase):

    def setUp(self):
        self.provider = spotify.SpotifyArtistImageProvider(client_id='id', client_secret='secret')

    def test_the_provider_is_named_after_its_source(self):
        self.assertEqual(self.provider.name, 'spotify')

    def test_without_credentials_no_token_is_requested(self):
        with patch.dict('os.environ', {}, clear=True):
            provider = spotify.SpotifyArtistImageProvider()
        with patch.object(spotify, 'requests') as http:
            self.assertIsNone(provider._get_token())
            self.assertEqual(provider.get_artist_images('Angerfist'), [])
        http.post.assert_not_called()

    def test_the_token_is_fetched_once_and_then_reused(self):
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            self.assertEqual(self.provider._get_token(), 'tok')
            self.assertEqual(self.provider._get_token(), 'tok')
        self.assertEqual(http.post.call_count, 1)

    def test_a_rejected_token_request_leaves_the_provider_without_a_token(self):
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(status_code=401)
            self.assertIsNone(self.provider._get_token())

    def test_a_token_request_that_raises_is_swallowed(self):
        with patch.object(spotify, 'requests') as http:
            http.post.side_effect = RuntimeError('network down')
            self.assertIsNone(self.provider._get_token())

    def test_a_search_turns_every_image_of_every_hit_into_a_candidate(self):
        payload = {'artists': {'items': [
            {'id': 'sp1', 'name': 'Angerfist', 'popularity': 60, 'genres': ['hardcore'],
             'followers': {'total': 1000},
             'images': [{'url': 'https://img.test/a.jpg', 'width': 640, 'height': 640},
                        {'url': 'https://img.test/b.jpg', 'width': 320, 'height': 320}]},
        ]}}
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
        artist = {'id': 'sp9', 'name': 'Angerfist', 'popularity': 70, 'genres': [],
                  'followers': {'total': 5}, 'images': [{'url': 'https://img.test/x.jpg', 'width': 1, 'height': 1}]}
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            http.get.return_value = make_response(payload=artist)
            candidates = self.provider.get_artist_images('Angerfist', external_ids={'spotify': 'sp9'})
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]['is_known_match'])
        self.assertIn('/artists/sp9', http.get.call_args.args[0])

    def test_a_non_200_search_yields_no_candidates(self):
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            http.get.return_value = make_response(status_code=429)
            self.assertEqual(self.provider.get_artist_images('Angerfist'), [])

    def test_a_transport_error_during_search_yields_no_candidates(self):
        with patch.object(spotify, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            http.get.side_effect = RuntimeError('network down')
            self.assertEqual(self.provider.get_artist_images('Angerfist'), [])


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
            http.get.return_value = make_response(payload={'artists': [{'id': 'mb1', 'name': 'Angerfist'}, {'id': 'mb2'}]})
            metadata = self.provider.get_artist_metadata('Angerfist')
        self.assertEqual(metadata['mbid'], 'mb1')
        self.assertEqual(metadata['name'], 'Angerfist')
        self.assertEqual(http.get.call_args.kwargs['params']['query'], 'artist:Angerfist')

    def test_a_search_without_hits_returns_nothing(self):
        with patch.object(musicbrainz, 'requests') as http:
            http.get.return_value = make_response(payload={'artists': []})
            self.assertIsNone(self.provider.get_artist_metadata('Nobody'))

    def test_a_lookup_by_mbid_uses_the_direct_url_and_reads_the_relations(self):
        payload = {'id': 'mb1', 'name': 'Angerfist', 'relations': [
            {'target-type': 'url', 'url': {'resource': 'https://open.spotify.com/artist/sp1?si=x'}},
            {'target-type': 'url', 'url': {'resource': 'https://soundcloud.com/angerfist'}},
            {'target-type': 'url', 'url': {'resource': 'https://www.last.fm/music/Angerfist'}},
            {'target-type': 'url', 'url': {'resource': 'https://example.test/other'}},
        ]}
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
