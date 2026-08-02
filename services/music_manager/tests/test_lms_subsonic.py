import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.music_manager import lms_subsonic


class NormalizeSongTest(unittest.TestCase):

    def test_maps_subsonic_song_to_internal_shape(self):
        song = {
            'id': 'tr-42', 'title': 'Song', 'artist': 'Artist', 'album': 'Album',
            'coverArt': 'al-7', 'duration': 215,
        }
        self.assertEqual(lms_subsonic.normalize_song(song), {
            'track_id': 'tr-42', 'title': 'Song', 'artist': 'Artist', 'album': 'Album',
            'cover_art': 'al-7', 'duration_ms': 215000,
        })

    def test_drops_song_without_usable_duration(self):
        self.assertIsNone(lms_subsonic.normalize_song({'id': 'tr-1', 'duration': 0}))
        self.assertIsNone(lms_subsonic.normalize_song({'id': 'tr-1'}))

    def test_drops_song_without_id(self):
        self.assertIsNone(lms_subsonic.normalize_song({'duration': 100}))


class FetchCandidateTracksTest(unittest.TestCase):

    def _response(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    @patch('services.music_manager.lms_subsonic.requests.get')
    def test_uses_random_songs_when_no_genre(self, mock_get):
        mock_get.return_value = self._response({'subsonic-response': {'status': 'ok', 'randomSongs': {
            'song': [{'id': 'tr-1', 'title': 'A', 'artist': 'X', 'album': 'Y', 'duration': 100}]
        }}})
        tracks = lms_subsonic.fetch_candidate_tracks(None, size=5)
        self.assertEqual([t['track_id'] for t in tracks], ['tr-1'])
        url = mock_get.call_args[0][0]
        params = mock_get.call_args[1]['params']
        self.assertTrue(url.endswith('/rest/getRandomSongs'))
        self.assertEqual(params['size'], 5)
        self.assertEqual(params['f'], 'json')

    @patch('services.music_manager.lms_subsonic.requests.get')
    def test_uses_songs_by_genre_when_genre_given(self, mock_get):
        mock_get.return_value = self._response({'subsonic-response': {'status': 'ok', 'songsByGenre': {
            'song': [{'id': 'tr-2', 'title': 'B', 'artist': 'X', 'album': 'Y', 'duration': 120}]
        }}})
        tracks = lms_subsonic.fetch_candidate_tracks('hardstyle', size=5)
        self.assertEqual([t['track_id'] for t in tracks], ['tr-2'])
        url = mock_get.call_args[0][0]
        params = mock_get.call_args[1]['params']
        self.assertTrue(url.endswith('/rest/getSongsByGenre'))
        self.assertEqual(params['genre'], 'hardstyle')
        self.assertEqual(params['count'], 5)

    @patch('services.music_manager.lms_subsonic.requests.get')
    def test_raises_on_subsonic_error_status(self, mock_get):
        mock_get.return_value = self._response({'subsonic-response': {
            'status': 'failed', 'error': {'code': 40, 'message': 'Wrong username or password'}
        }})
        with self.assertRaises(RuntimeError):
            lms_subsonic.fetch_candidate_tracks(None)

    @patch('services.music_manager.lms_subsonic.requests.get')
    def test_handles_single_song_object_instead_of_list(self, mock_get):
        mock_get.return_value = self._response({'subsonic-response': {'status': 'ok', 'randomSongs': {
            'song': {'id': 'tr-9', 'title': 'Solo', 'artist': 'X', 'album': 'Y', 'duration': 90}
        }}})
        tracks = lms_subsonic.fetch_candidate_tracks(None)
        self.assertEqual([t['track_id'] for t in tracks], ['tr-9'])
