import sys
import types
import unittest
orig_requests = sys.modules.get('requests')
orig_yt_dlp = sys.modules.get('yt_dlp')
sys.modules['requests'] = types.ModuleType('requests')
sys.modules['yt_dlp'] = types.ModuleType('yt_dlp')

orig_helpers = sys.modules.get('postprocessing.Song.Helpers.BrokenSongHelper')
helpers_mod = types.ModuleType('postprocessing.Song.Helpers.BrokenSongHelper')
helpers_mod.BrokenSongHelper = lambda *args, **kwargs: None
sys.modules['postprocessing.Song.Helpers.BrokenSongHelper'] = helpers_mod

orig_helpers2 = sys.modules.get('postprocessing.Song.Helpers.BrokenSongArtistLookupHelper')
helpers_mod2 = types.ModuleType('postprocessing.Song.Helpers.BrokenSongArtistLookupHelper')
helpers_mod2.BrokenSongArtistLookupHelper = lambda *args, **kwargs: types.SimpleNamespace(insert_if_missing=lambda *a, **k: None, get_normalized_name=lambda *a, **k: 'artist')
sys.modules['postprocessing.Song.Helpers.BrokenSongArtistLookupHelper'] = helpers_mod2

try:
    from services.other.repair import FileRepair
    from services.common.Helpers.DatabaseConnector import DatabaseConnector
finally:
    if orig_requests: sys.modules['requests'] = orig_requests
    else: sys.modules.pop('requests', None)
    if orig_yt_dlp: sys.modules['yt_dlp'] = orig_yt_dlp
    else: sys.modules.pop('yt_dlp', None)
    if orig_helpers: sys.modules['postprocessing.Song.Helpers.BrokenSongHelper'] = orig_helpers
    else: sys.modules.pop('postprocessing.Song.Helpers.BrokenSongHelper', None)
    if orig_helpers2: sys.modules['postprocessing.Song.Helpers.BrokenSongArtistLookupHelper'] = orig_helpers2
    else: sys.modules.pop('postprocessing.Song.Helpers.BrokenSongArtistLookupHelper', None)

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