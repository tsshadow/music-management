import unittest
from unittest.mock import MagicMock, patch
from services.tests.mock_base import setup_mocks, reset_database_helpers

setup_mocks()

from services.tagger.Song.SoundcloudSong import SoundcloudSong
from services.tagger.constants import TITLE, ARTIST

class TestSoundcloudPremiere(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        from services.common.Helpers.Cache import databaseHelpers
        databaseHelpers['library_artists'].get_all_values.return_value = ['Devin Wild']
        databaseHelpers['library_artists'].exists.return_value = True

    def test_premiere_split(self):
        """
        Test that 'Premiere: Artist - Title' in SoundCloud title is correctly handled.
        """
        path = '/tmp/soundcloud/Scantraxx/Premiere: Devin Wild - Blue.mp3'
        extra_info = {
            'uploader': 'Scantraxx',
            'title': 'Premiere: Devin Wild - Blue'
        }

        song = SoundcloudSong(path, extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()

        # Based on InferArtistFromPresentsOrColonRule:
        # re.search('\\b([A-Za-z0-9 &\\-_]+?)\\s*(presents:|:)', title, flags=re.IGNORECASE)
        # 'Premiere' matches group 1.
        # Wait, if 'Premiere' is the one before ':', then it might think 'Premiere' is the artist.
        # But 'Premiere' is likely NOT in library_artists.
        # If Devin Wild is in library_artists, we want IT to be found.

        # Let's check InferArtistFromPresentsOrColonRule again.
        # It looks for something BEFORE 'presents:' or ':'.
        # In 'Premiere: Devin Wild - Blue', 'Premiere' is before ':'.
        # If 'Premiere' is not in library_artists, it fails.
        # Then it moves to other rules.
        # InferArtistFromTitleSingleDashRule replaces '|' with '-' and checks 'Devin Wild - Blue'.

        self.assertEqual(song.artist(), 'Devin Wild')
        self.assertEqual(song.title(), 'Blue')

if __name__ == '__main__':
    unittest.main()
