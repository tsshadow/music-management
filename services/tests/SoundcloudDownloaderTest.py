import sys
import types
import unittest
import os
import tempfile
orig_yt_dlp = sys.modules.get('yt_dlp')
orig_yt_dlp_pp = sys.modules.get('yt_dlp.postprocessor')
yt_dlp_mod = types.ModuleType('yt_dlp')
yt_dlp_mod.YoutubeDL = lambda *a, **k: None
postproc_module = types.ModuleType('yt_dlp.postprocessor')
postproc_module.FFmpegMetadataPP = lambda *a, **k: None
postproc_module.EmbedThumbnailPP = lambda *a, **k: None

class DummyPP:
    pass
postproc_module.PostProcessor = DummyPP
sys.modules['yt_dlp'] = yt_dlp_mod
sys.modules['yt_dlp.postprocessor'] = postproc_module

orig_db_connector = sys.modules.get('postprocessing.Song.Helpers.DatabaseConnector')
mock_db = types.ModuleType('postprocessing.Song.Helpers.DatabaseConnector')

class DummyConnector:

    def connect(self):

        class Conn:

            def cursor(self):

                class Ctx:

                    def __enter__(self_inner):
                        return self_inner

                    def __exit__(self_inner, exc_type, exc, tb):
                        pass

                    def execute(self_inner, *args, **kwargs):
                        pass

                    def fetchall(self_inner):
                        return []
                return Ctx()
        return Conn()
mock_db.DatabaseConnector = DummyConnector
sys.modules['postprocessing.Song.Helpers.DatabaseConnector'] = mock_db

orig_sc_song = sys.modules.get('postprocessing.Song.SoundcloudSong')
sc_song_mod = types.ModuleType('postprocessing.Song.SoundcloudSong')
sc_song_mod.SoundcloudSong = lambda *a, **k: None
sys.modules['postprocessing.Song.SoundcloudSong'] = sc_song_mod

orig_archive = sys.modules.get('soundcloud.SoundcloudArchive')
sc_archive_mod = types.ModuleType('soundcloud.SoundcloudArchive')

class DummyArchive:

    @staticmethod
    def exists(*a, **k):
        return False

    @staticmethod
    def insert(*a, **k):
        pass
sc_archive_mod.SoundcloudArchive = DummyArchive
sys.modules['soundcloud.SoundcloudArchive'] = sc_archive_mod

try:
    from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
finally:
    # Restore modules after import so they don't leak into other tests during collection
    if orig_yt_dlp: sys.modules['yt_dlp'] = orig_yt_dlp
    else: sys.modules.pop('yt_dlp', None)
    if orig_yt_dlp_pp: sys.modules['yt_dlp.postprocessor'] = orig_yt_dlp_pp
    else: sys.modules.pop('yt_dlp.postprocessor', None)
    if orig_db_connector: sys.modules['postprocessing.Song.Helpers.DatabaseConnector'] = orig_db_connector
    else: sys.modules.pop('postprocessing.Song.Helpers.DatabaseConnector', None)
    if orig_sc_song: sys.modules['postprocessing.Song.SoundcloudSong'] = orig_sc_song
    else: sys.modules.pop('postprocessing.Song.SoundcloudSong', None)
    if orig_archive: sys.modules['soundcloud.SoundcloudArchive'] = orig_archive
    else: sys.modules.pop('soundcloud.SoundcloudArchive', None)

class SoundcloudDownloaderTest(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ['soundcloud_folder'] = self.tempdir.name
        os.environ['soundcloud_archive'] = os.path.join(self.tempdir.name, 'arc.txt')
        open(os.environ['soundcloud_archive'], 'w').close()

    def tearDown(self):
        self.tempdir.cleanup()
        if orig_archive is not None:
            sys.modules['soundcloud.SoundcloudArchive'] = orig_archive
        else:
            sys.modules.pop('soundcloud.SoundcloudArchive', None)
        sys.modules.pop('postprocessing.Song.SoundcloudSong', None)

    def test_match_filter(self):
        dl = SoundcloudDownloader()
        too_short = {'duration': 30, 'title': 'a'}
        self.assertIsNotNone(dl._match_filter(too_short))
        ok = {'duration': 100, 'title': 'b'}
        self.assertIsNone(dl._match_filter(ok))
        too_long = {'duration': 30000, 'title': 'c'}
        self.assertIsNotNone(dl._match_filter(too_long))
if __name__ == '__main__':
    unittest.main()