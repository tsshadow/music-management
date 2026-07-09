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
        # Artist -> Genre rule
        databaseHelpers['artistGenreHelper'].get.side_effect = lambda x: ['Hardstyle'] if x == 'Albino' else []
        databaseHelpers['rules_genres'].exists.return_value = True

    def test_genre_from_artist(self):
        """
        Test that genre is inferred from artist if not present.
        """
        path = '/tmp/soundcloud/Albino/RIJE MOAT.mp3'
        extra_info = {
            'uploader': 'Albino',
            'title': 'RIJE MOAT',
            'genre': None # No genre in metadata
        }

        song = SoundcloudSong(path, extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        # We need to make sure Artist is set to 'Albino' so the rule can find it
        # SoundcloudSong sets album artist from path
        song.parse()

        # InferGenreFromArtistRule should find 'Albino' and set genre to 'Hardstyle'
        self.assertEqual(song.genre(), 'Hardstyle')

if __name__ == '__main__':
    unittest.main()
