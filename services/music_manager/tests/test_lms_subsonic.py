import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.music_manager import lms_subsonic


class NormalizeSongTest(unittest.TestCase):
    def test_maps_subsonic_song_to_internal_shape(self):
        song = {
            'id': 'tr-42',
            'title': 'Song',
            'artist': 'Artist',
            'album': 'Album',
            'coverArt': 'al-7',
            'duration': 215,
        }
        self.assertEqual(
            lms_subsonic.normalize_song(song),
            {
                'track_id': 'tr-42',
                'title': 'Song',
                'artist': 'Artist',
                'album': 'Album',
                'cover_art': 'al-7',
                'duration_ms': 215000,
            },
        )

    def test_drops_song_without_usable_duration(self):
        self.assertIsNone(lms_subsonic.normalize_song({'id': 'tr-1', 'duration': 0}))
        self.assertIsNone(lms_subsonic.normalize_song({'id': 'tr-1'}))

    def test_drops_song_without_id(self):
        self.assertIsNone(lms_subsonic.normalize_song({'duration': 100}))


class BuildFilterParamsTest(unittest.TestCase):
    def test_empty_filter_sends_nothing(self):
        self.assertEqual(lms_subsonic.build_filter_params({}), {})
        self.assertEqual(lms_subsonic.build_filter_params(None), {})

    def test_maps_stored_keys_to_subsonic_parameters(self):
        params = lms_subsonic.build_filter_params(
            {
                'label': 'Q-dance Records',
                'genre': 'hardstyle',
                'artist': 'Headhunterz',
                'length': 'short',
                'year': '2024',
                'rating_min': 4,
                'rating_max': 5,
                'duration_min': 60,
                'duration_max': 300,
            }
        )
        self.assertEqual(
            params,
            {
                'label': 'Q-dance Records',
                'genre': 'hardstyle',
                'artist': 'Headhunterz',
                'length': 'short',
                'year': '2024',
                'ratingMin': 4,
                'ratingMax': 5,
                'durationMin': 60,
                'durationMax': 300,
            },
        )

    def test_drops_blank_and_missing_values(self):
        params = lms_subsonic.build_filter_params({'label': '  ', 'genre': None, 'artist': 'X'})
        self.assertEqual(params, {'artist': 'X'})

    def test_include_unrated_only_travels_with_a_rating_bound(self):
        self.assertNotIn('includeUnrated', lms_subsonic.build_filter_params({'include_unrated': True}))
        self.assertEqual(
            lms_subsonic.build_filter_params({'rating_min': 4, 'include_unrated': True})['includeUnrated'],
            'true',
        )

    def test_include_unrated_false_is_left_to_the_server_default(self):
        self.assertNotIn(
            'includeUnrated',
            lms_subsonic.build_filter_params({'rating_min': 4, 'include_unrated': False}),
        )


class FetchCandidateTracksTest(unittest.TestCase):
    def setUp(self):
        # lms_base_url() no longer invents a host, so these tests have to say
        # where LMS is. Before, they leaned on the removed `http://lms:5082`
        # default -- the same default that sent an unconfigured container to
        # production.
        env = patch.dict(
            'os.environ',
            {'LMS_URL': 'http://lms-under-test:5082', 'LMS_HOSTS': '', 'MUMA_SERVER_HOSTS': ''},
            clear=False,
        )
        env.start()
        self.addCleanup(env.stop)

    def _response(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    def _songs(self, *songs):
        return self._response({'subsonic-response': {'status': 'ok', 'songsByFilter': {'song': list(songs)}}})

    @patch('services.music_manager.lms_subsonic.requests.get')
    def test_empty_filter_draws_from_the_whole_library(self, mock_get):
        mock_get.return_value = self._songs({'id': 'tr-1', 'title': 'A', 'artist': 'X', 'album': 'Y', 'duration': 100})
        tracks = lms_subsonic.fetch_candidate_tracks({}, size=5)
        self.assertEqual([t['track_id'] for t in tracks], ['tr-1'])
        url = mock_get.call_args[0][0]
        params = mock_get.call_args[1]['params']
        self.assertTrue(url.endswith('/rest/getSongsByFilter'))
        self.assertEqual(params['count'], 5)
        self.assertEqual(params['f'], 'json')
        self.assertNotIn('label', params)

    @patch('services.music_manager.lms_subsonic.requests.get')
    def test_sends_the_channel_filter(self, mock_get):
        mock_get.return_value = self._songs({'id': 'tr-2', 'title': 'B', 'artist': 'X', 'album': 'Y', 'duration': 120})
        tracks = lms_subsonic.fetch_candidate_tracks({'label': 'Dirty Workz', 'length': 'short'}, size=5)
        self.assertEqual([t['track_id'] for t in tracks], ['tr-2'])
        params = mock_get.call_args[1]['params']
        self.assertEqual(params['label'], 'Dirty Workz')
        self.assertEqual(params['length'], 'short')

    @patch('services.music_manager.lms_subsonic.requests.get')
    def test_raises_on_subsonic_error_status(self, mock_get):
        mock_get.return_value = self._response(
            {'subsonic-response': {'status': 'failed', 'error': {'code': 40, 'message': 'Wrong username or password'}}}
        )
        with self.assertRaises(RuntimeError) as ctx:
            lms_subsonic.fetch_candidate_tracks({})

        self.assertNotIsInstance(ctx.exception, lms_subsonic.LmsNotConfigured)
        self.assertIn('Wrong username or password', str(ctx.exception))
        mock_get.assert_called_once()

    @patch('services.music_manager.lms_subsonic.requests.get')
    def test_handles_single_song_object_instead_of_list(self, mock_get):
        mock_get.return_value = self._response(
            {
                'subsonic-response': {
                    'status': 'ok',
                    'songsByFilter': {
                        'song': {'id': 'tr-9', 'title': 'Solo', 'artist': 'X', 'album': 'Y', 'duration': 90}
                    },
                }
            }
        )
        tracks = lms_subsonic.fetch_candidate_tracks({})
        self.assertEqual([t['track_id'] for t in tracks], ['tr-9'])


class LmsBaseUrlTest(unittest.TestCase):
    """Where the radio sends its requests, which is not a thing to guess.

    The removed default was `http://lms:5082`. That is correct on the deployment,
    where `lms` is a container on the shared network -- and that is what made it
    dangerous elsewhere: on the office LAN the same bare name resolves to
    production, so an unconfigured container called prod every five seconds.
    """

    def _env(self, **values):
        """Clear all three variables, then set only the ones given."""
        cleared = dict.fromkeys(('LMS_URL', 'LMS_HOSTS', 'MUMA_SERVER_HOSTS'), '')
        return patch.dict('os.environ', {**cleared, **values}, clear=False)

    def test_lms_url_wins(self):
        with self._env(LMS_URL='http://a:1', LMS_HOSTS='b:2', MUMA_SERVER_HOSTS='c:3'):
            self.assertEqual(lms_subsonic.lms_base_url(), 'http://a:1')

    def test_lms_hosts_is_used_when_lms_url_is_absent(self):
        with self._env(LMS_HOSTS='b:2', MUMA_SERVER_HOSTS='c:3'):
            self.assertEqual(lms_subsonic.lms_base_url(), 'http://b:2')

    def test_muma_server_hosts_is_read(self):
        """The variable compose actually sets for this service.

        The old code did not read it, so the deployment worked by coincidence:
        the hardcoded default happened to equal the configured value.
        """
        with self._env(MUMA_SERVER_HOSTS='lms:5082'):
            self.assertEqual(lms_subsonic.lms_base_url(), 'http://lms:5082')

    def test_only_the_first_host_of_a_list_is_used(self):
        with self._env(LMS_HOSTS='first:1,second:2'):
            self.assertEqual(lms_subsonic.lms_base_url(), 'http://first:1')

    def test_scheme_is_added_when_missing_and_kept_when_present(self):
        with self._env(LMS_HOSTS='plain:5082'):
            self.assertEqual(lms_subsonic.lms_base_url(), 'http://plain:5082')
        with self._env(LMS_HOSTS='https://secure:443'):
            self.assertEqual(lms_subsonic.lms_base_url(), 'https://secure:443')

    def test_trailing_slash_is_stripped(self):
        with self._env(LMS_URL='http://a:1/'):
            self.assertEqual(lms_subsonic.lms_base_url(), 'http://a:1')

    def test_blank_and_whitespace_values_do_not_count_as_configured(self):
        with self._env(LMS_URL='   ', LMS_HOSTS=' , '):
            with self.assertRaises(lms_subsonic.LmsNotConfigured):
                lms_subsonic.lms_base_url()

    def test_nothing_configured_raises_instead_of_guessing_a_host(self):
        """The regression this change exists for: no silent fallback, ever."""
        with self._env():
            with self.assertRaises(lms_subsonic.LmsNotConfigured) as ctx:
                lms_subsonic.lms_base_url()

        message = str(ctx.exception)
        self.assertIn('MUMA_SERVER_HOSTS', message)
        # The old default must not come back as a suggestion either.
        self.assertNotIn('http://lms:5082', message)
