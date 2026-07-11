import unittest
from unittest.mock import MagicMock, patch
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.tagger.Song.SoundcloudSong import SoundcloudSong
from services.tagger.Song.BaseSong import BaseSong
from services.tagger.constants import TITLE, ARTIST, REMIXER

class TestSoundcloudArtistTitle(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        from services.common.Helpers.Cache import databaseHelpers
        self.mock_artists = ['Albino', 'Qriminal', 'Devin Wild', 'Hard Driver', 'Sub Zero Project']
        databaseHelpers['library_artists'].get_all_values.return_value = self.mock_artists
        databaseHelpers['library_artists'].exists.side_effect = lambda x: x in self.mock_artists

    def test_single_artist_title_split(self):
        """
        Test that 'Artist - Title' in SoundCloud title is correctly split.
        """
        path = '/tmp/soundcloud/Albino/Albino - RIJE MOAT.mp3'
        extra_info = {'uploader': 'Albino', 'title': 'Albino - RIJE MOAT'}
        song = SoundcloudSong(path, extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        print(song)
        self.assertEqual(song.artist(), 'Albino')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_multi_artist_title_split(self):
        """
        Test that 'Artist - Title' in SoundCloud title is correctly split.
        """
        path = '/tmp/soundcloud/Albino/Albino - RIJE MOAT.mp3'
        extra_info = {'uploader': 'Albino', 'title': 'Albino & Qriminal - RIJE MOAT'}
        song = SoundcloudSong(path, extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        print(song)
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_x_artist_title_split(self):
        """Test 'Artist x Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino x Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_feat_artist_title_split(self):
        """Test 'Artist feat. Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino feat. Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_ft_artist_title_split(self):
        """Test 'Artist ft Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino ft Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_comma_artist_title_split(self):
        """Test 'Artist, Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino, Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_vs_artist_title_split(self):
        """Test 'Artist vs. Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino vs. Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_presents_artist_title_split(self):
        """Test 'Artist presents Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino presents RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_colon_artist_title_split(self):
        """Test 'Artist: Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino: RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_pipe_separator_split(self):
        """Test 'Artist - Title | Part'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino - RIJE MOAT | Blue'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino')
        self.assertEqual(song.title(), 'RIJE MOAT - Blue')

    def test_complex_multi_part(self):
        """Test 'Defqon 2025 | Devin Wild | Blue'"""
        extra_info = {'uploader': 'Q-dance', 'title': 'Defqon 2025 | Devin Wild | Blue'}
        song = SoundcloudSong('/tmp/soundcloud/Q-dance/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Devin Wild')
        self.assertIn('Defqon 2025', song.title())
        self.assertIn('Blue', song.title())

    def test_premiere_prefix(self):
        """Test 'Premiere: Artist - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Premiere: Albino - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_multi_artist_with_feat(self):
        """Test 'Artist & Artist2 feat. Artist3 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino & Qriminal feat. Hard Driver - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal;Hard Driver')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_remix_in_title(self):
        """Test 'Artist - Title (Remixer Remix)'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino - RIJE MOAT (Qriminal Remix)'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT (Qriminal Remix)')
        self.assertEqual(song.tag_collection.get_item_as_string(REMIXER), 'Qriminal')

    def test_feat_in_parentheses(self):
        """Test 'Artist - Title (feat. Artist2)'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino - RIJE MOAT (feat. Qriminal)'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_label_in_brackets(self):
        """Test 'Artist [Label] - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino [Scantraxx] - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_mixed_separators(self):
        """Test 'Artist, Artist2 & Artist3 x Artist4 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino, Qriminal & Hard Driver x Sub Zero Project - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal;Hard Driver;Sub Zero Project')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_artist_with_and_in_name(self):
        """Test artist that has 'and' in their name (if they were in DB)"""
        extra_info = {'uploader': 'Sub Zero Project', 'title': 'Sub Zero Project - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Sub Zero Project/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Sub Zero Project')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_b2b_artist_title_split(self):
        """Test 'Artist b2b Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino b2b Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_with_artist_title_split(self):
        """Test 'Artist with Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino with Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_meets_artist_title_split(self):
        """Test 'Artist meets Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino meets Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_aka_artist_title_split(self):
        """Test 'Artist aka Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino aka Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_vs_no_dot_artist_title_split(self):
        """Test 'Artist vs Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino vs Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_invite_artist_title_split(self):
        """Test 'Artist invite Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino invite Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')

    def test_et_artist_title_split(self):
        """Test 'Artist et Artist2 - Title'"""
        extra_info = {'uploader': 'Albino', 'title': 'Albino et Qriminal - RIJE MOAT'}
        song = SoundcloudSong('/tmp/soundcloud/Albino/track.mp3', extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino;Qriminal')
        self.assertEqual(song.title(), 'RIJE MOAT')
if __name__ == '__main__':
    unittest.main()