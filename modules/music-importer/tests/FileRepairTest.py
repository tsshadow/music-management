import sys
import types
import unittest

# stub external dependencies
sys.modules['requests'] = types.ModuleType('requests')
sys.modules['yt_dlp'] = types.ModuleType('yt_dlp')

helpers_mod = types.ModuleType('postprocessing.Song.Helpers.BrokenSongHelper')
helpers_mod.BrokenSongHelper = lambda *args, **kwargs: None
sys.modules['postprocessing.Song.Helpers.BrokenSongHelper'] = helpers_mod

helpers_mod2 = types.ModuleType('postprocessing.Song.Helpers.BrokenSongArtistLookupHelper')
helpers_mod2.BrokenSongArtistLookupHelper = lambda *args, **kwargs: types.SimpleNamespace(insert_if_missing=lambda *a, **k: None,
                                                                                        get_normalized_name=lambda *a, **k: 'artist')
sys.modules['postprocessing.Song.Helpers.BrokenSongArtistLookupHelper'] = helpers_mod2

from postprocessing.repair import FileRepair

class FileRepairTest(unittest.TestCase):
    def test_derive_soundcloud_url(self):
        fr = FileRepair()
        path = '/Music/Soundcloud/artist/Track Title.m4a'
        expected = 'https://soundcloud.com/artist/track-title'
        self.assertEqual(fr.derive_soundcloud_url(path), expected)

    def test_derive_youtube_url(self):
        fr = FileRepair()
        path = '/Music/Youtube/uploader/Video Title.m4a'
        expected = 'https://www.youtube.com/watch?v=video-title'
        self.assertEqual(fr.derive_youtube_url(path), expected)

if __name__ == '__main__':
    unittest.main()
