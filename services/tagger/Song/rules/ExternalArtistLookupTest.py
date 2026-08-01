import unittest
from unittest.mock import MagicMock, patch

from services.tagger.Song.rules import ExternalArtistLookup as module
from services.tagger.Song.rules.ExternalArtistLookup import (
    DiscogsLookup, ExternalArtistLookup, LastfmLookup, MusicBrainzLookup, SpotifyLookup)


def make_response(status_code=200, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload if payload is not None else {}
    return response


class DiscogsLookupTest(unittest.TestCase):

    def setUp(self):
        self.lookup = DiscogsLookup(token='tok')

    def test_without_a_token_no_request_is_made(self):
        with patch.dict('os.environ', {}, clear=True):
            lookup = DiscogsLookup()
        with patch.object(module, 'requests') as http:
            self.assertFalse(lookup.is_known_artist('Angerfist'))
        http.get.assert_not_called()

    def test_an_exact_title_match_counts_as_known(self):
        with patch.object(module, 'requests') as http:
            http.get.return_value = make_response(payload={'results': [{'title': 'angerfist'}]})
            self.assertTrue(self.lookup.is_known_artist('Angerfist'))

    def test_a_near_miss_does_not_count(self):
        with patch.object(module, 'requests') as http:
            http.get.return_value = make_response(payload={'results': [{'title': 'Angerfist & Outsiders'}]})
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))

    def test_a_non_200_response_counts_as_unknown(self):
        with patch.object(module, 'requests') as http:
            http.get.return_value = make_response(status_code=429)
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))

    def test_a_transport_error_counts_as_unknown(self):
        with patch.object(module, 'requests') as http:
            http.get.side_effect = RuntimeError('network down')
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))


class MusicBrainzLookupTest(unittest.TestCase):

    def setUp(self):
        self.lookup = MusicBrainzLookup()

    def test_an_exact_name_match_counts_as_known(self):
        with patch.object(module, 'requests') as http:
            http.get.return_value = make_response(payload={'artists': [{'name': 'Angerfist'}]})
            self.assertTrue(self.lookup.is_known_artist('angerfist'))

    def test_a_different_name_does_not_count(self):
        with patch.object(module, 'requests') as http:
            http.get.return_value = make_response(payload={'artists': [{'name': 'Radical Redemption'}]})
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))

    def test_a_non_200_response_counts_as_unknown(self):
        with patch.object(module, 'requests') as http:
            http.get.return_value = make_response(status_code=503)
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))

    def test_a_transport_error_counts_as_unknown(self):
        with patch.object(module, 'requests') as http:
            http.get.side_effect = RuntimeError('network down')
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))


class LastfmLookupTest(unittest.TestCase):

    def setUp(self):
        self.lookup = LastfmLookup(api_key='key')

    def test_without_an_api_key_no_request_is_made(self):
        with patch.dict('os.environ', {}, clear=True):
            lookup = LastfmLookup()
        with patch.object(module, 'requests') as http:
            self.assertFalse(lookup.is_known_artist('Angerfist'))
        http.get.assert_not_called()

    def test_an_exact_name_match_counts_as_known(self):
        with patch.object(module, 'requests') as http:
            http.get.return_value = make_response(payload={'artist': {'name': 'Angerfist'}})
            self.assertTrue(self.lookup.is_known_artist('ANGERFIST'))

    def test_an_empty_result_does_not_count(self):
        with patch.object(module, 'requests') as http:
            http.get.return_value = make_response(payload={})
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))

    def test_a_non_200_response_counts_as_unknown(self):
        with patch.object(module, 'requests') as http:
            http.get.return_value = make_response(status_code=403)
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))

    def test_a_transport_error_counts_as_unknown(self):
        with patch.object(module, 'requests') as http:
            http.get.side_effect = RuntimeError('network down')
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))


class SpotifyLookupTest(unittest.TestCase):

    def setUp(self):
        self.lookup = SpotifyLookup(client_id='id', client_secret='secret')

    def test_without_credentials_there_is_no_token(self):
        with patch.dict('os.environ', {}, clear=True):
            lookup = SpotifyLookup()
        self.assertIsNone(lookup._get_token())

    def test_the_token_is_fetched_once_and_then_reused(self):
        with patch.object(module, 'requests') as http:
            http.post.return_value = make_response(payload={'access_token': 'tok'})
            self.assertEqual(self.lookup._get_token(), 'tok')
            self.assertEqual(self.lookup._get_token(), 'tok')
        self.assertEqual(http.post.call_count, 1)

    def test_a_rejected_token_request_leaves_no_token(self):
        with patch.object(module, 'requests') as http:
            http.post.return_value = make_response(status_code=401)
            self.assertIsNone(self.lookup._get_token())

    def test_a_token_request_that_raises_leaves_no_token(self):
        with patch.object(module, 'requests') as http:
            http.post.side_effect = RuntimeError('network down')
            self.assertIsNone(self.lookup._get_token())

    def test_without_a_token_the_search_is_skipped(self):
        with patch.object(self.lookup, '_get_token', return_value=None), \
             patch.object(module, 'requests') as http:
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))
        http.get.assert_not_called()

    def test_an_exact_name_match_counts_as_known(self):
        with patch.object(self.lookup, '_get_token', return_value='tok'), \
             patch.object(module, 'requests') as http:
            http.get.return_value = make_response(payload={'artists': {'items': [{'name': 'Angerfist'}]}})
            self.assertTrue(self.lookup.is_known_artist('angerfist'))

    def test_a_different_name_does_not_count(self):
        with patch.object(self.lookup, '_get_token', return_value='tok'), \
             patch.object(module, 'requests') as http:
            http.get.return_value = make_response(payload={'artists': {'items': [{'name': 'Someone Else'}]}})
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))

    def test_a_non_200_search_counts_as_unknown(self):
        with patch.object(self.lookup, '_get_token', return_value='tok'), \
             patch.object(module, 'requests') as http:
            http.get.return_value = make_response(status_code=429)
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))

    def test_a_transport_error_counts_as_unknown(self):
        with patch.object(self.lookup, '_get_token', return_value='tok'), \
             patch.object(module, 'requests') as http:
            http.get.side_effect = RuntimeError('network down')
            self.assertFalse(self.lookup.is_known_artist('Angerfist'))


class ExternalArtistLookupTest(unittest.TestCase):

    def setUp(self):
        self.lookup = ExternalArtistLookup()

    def test_all_four_services_are_consulted(self):
        self.assertEqual([service.name for service in self.lookup.services],
                         ['Discogs', 'MusicBrainz', 'Last.fm', 'Spotify'])

    def test_the_first_service_that_knows_the_artist_ends_the_search(self):
        first, second = MagicMock(name='Discogs'), MagicMock(name='MusicBrainz')
        first.is_known_artist.return_value = True
        self.lookup.services = [first, second]
        with patch('builtins.print'):
            self.assertTrue(self.lookup.is_known_artist('Angerfist'))
        second.is_known_artist.assert_not_called()

    def test_an_artist_no_service_knows_is_reported_as_unknown(self):
        for service in self.lookup.services:
            service.is_known_artist = MagicMock(return_value=False)
        self.assertFalse(self.lookup.is_known_artist('Nobody At All'))

    def test_a_service_that_blows_up_does_not_stop_the_others(self):
        broken, working = MagicMock(), MagicMock()
        broken.is_known_artist.side_effect = RuntimeError('api down')
        working.is_known_artist.return_value = True
        self.lookup.services = [broken, working]
        with patch('builtins.print'):
            self.assertTrue(self.lookup.is_known_artist('Angerfist'))


if __name__ == '__main__':
    unittest.main()
