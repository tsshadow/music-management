import sys
import types
import unittest
# sys.modules['numpy'] = types.ModuleType('numpy')
# numpy_testing = types.ModuleType('numpy.testing')
# numpy_testing.print_coercion_tables = lambda *a, **k: None
# sys.modules['numpy.testing'] = numpy_testing
# pc = types.ModuleType('numpy.testing.print_coercion_tables')
# pc.print_new_cast_table = lambda *a, **k: None
# sys.modules['numpy.testing.print_coercion_tables'] = pc
orig_db_connector = sys.modules.get('postprocessing.Song.Helpers.DatabaseConnector')
db_module = types.ModuleType('postprocessing.Song.Helpers.DatabaseConnector')

class DummyConnector:

    def connect(self):

        class Conn:

            def cursor(self):

                class Ctx:

                    def __enter__(self_inner):
                        return self_inner

                    def __exit__(self_inner, exc_type, exc, tb):
                        pass

                    def execute(self_inner, *a, **k):
                        pass

                    def fetchone(self_inner):
                        return None
                return Ctx()
        return Conn()
db_module.DatabaseConnector = DummyConnector
sys.modules['postprocessing.Song.Helpers.DatabaseConnector'] = db_module

orig_yt_dlp = sys.modules.get('yt_dlp')
orig_yt_dlp_pp = sys.modules.get('yt_dlp.postprocessor')
postproc_module = types.ModuleType('yt_dlp.postprocessor')

class DummyPP:
    pass
postproc_module.PostProcessor = DummyPP
sys.modules['yt_dlp'] = types.ModuleType('yt_dlp')
sys.modules['yt_dlp'].postprocessor = postproc_module
sys.modules['yt_dlp.postprocessor'] = postproc_module

orig_sc_song = sys.modules.get('postprocessing.Song.SoundcloudSong')
sc_song_mod = types.ModuleType('postprocessing.Song.SoundcloudSong')
sc_song_mod.SoundcloudSong = lambda *a, **k: None
sys.modules['postprocessing.Song.SoundcloudSong'] = sc_song_mod

try:
    from services.downloader.soundcloud.SoundcloudSongProcessor import SoundcloudSongProcessor
finally:
    if orig_db_connector: sys.modules['postprocessing.Song.Helpers.DatabaseConnector'] = orig_db_connector
    else: sys.modules.pop('postprocessing.Song.Helpers.DatabaseConnector', None)
    if orig_yt_dlp: sys.modules['yt_dlp'] = orig_yt_dlp
    else: sys.modules.pop('yt_dlp', None)
    if orig_yt_dlp_pp: sys.modules['yt_dlp.postprocessor'] = orig_yt_dlp_pp
    else: sys.modules.pop('yt_dlp.postprocessor', None)
    if orig_sc_song: sys.modules['postprocessing.Song.SoundcloudSong'] = orig_sc_song
    else: sys.modules.pop('postprocessing.Song.SoundcloudSong', None)

class SoundcloudProcessorTest(unittest.TestCase):

    def tearDown(self):
        pass

    def test_extract_account_name_from_url(self):
        url = 'https://soundcloud.com/testuser/track-name'
        self.assertEqual(SoundcloudSongProcessor._extract_account_name_from_url(url), 'testuser')

    def test_extract_account_name_from_url_invalid(self):
        self.assertEqual(SoundcloudSongProcessor._extract_account_name_from_url('not a url'), 'not a url')
if __name__ == '__main__':
    unittest.main()