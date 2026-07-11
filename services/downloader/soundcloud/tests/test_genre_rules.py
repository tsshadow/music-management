import unittest
from unittest.mock import MagicMock, patch
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.tagger.Song.SoundcloudSong import SoundcloudSong
from services.tagger.constants import TITLE, ARTIST, GENRE

class TestSoundcloudGenreRules(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        from services.common.Helpers.Cache import databaseHelpers
        databaseHelpers['artistGenreHelper'].get.side_effect = lambda x: ['Hardstyle'] if x == 'Albino' else []
        databaseHelpers['rules_genres'].exists.return_value = True

    def test_genre_from_artist(self):
        """
        Test that genre is inferred from artist if not present.
        """
        path = '/tmp/soundcloud/Albino/RIJE MOAT.mp3'
        extra_info = {'uploader': 'Albino', 'title': 'RIJE MOAT', 'genre': None}
        song = SoundcloudSong(path, extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.genre(), 'Hardstyle')
if __name__ == '__main__':
    unittest.main()