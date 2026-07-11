import os
import sys
import types
from unittest.mock import MagicMock
# Force mock mutagen
mutagen_mod = types.ModuleType('mutagen')
mutagen_mod.MutagenError = Exception
sys.modules['mutagen'] = mutagen_mod
for sub in ['easyid3', 'mp3', 'easymp4', 'flac', 'mp4', 'oggopus', 'wave', 'id3']:
    sub_mod = types.ModuleType(f'mutagen.{sub}')
    sys.modules[f'mutagen.{sub}'] = sub_mod
    setattr(mutagen_mod, sub, sub_mod)
MockEasyID3 = type('EasyID3', (dict,), {'save': lambda self, *a, **k: None, 'RegisterTXXXKey': staticmethod(lambda k, d: None)})
MockEasyID3.__module__ = 'mutagen.easyid3'
sys.modules['mutagen.easyid3'].EasyID3 = MockEasyID3
MockMP3 = type('MP3', (dict,), {'__init__': lambda self, *a, **k: (super(type(self), self).__init__(), setattr(self, 'tags', MockEasyID3()), setattr(self, 'info', MagicMock(length=180)), None)[-1], 'save': lambda self, *a, **k: None})
MockMP3.__module__ = 'mutagen.mp3'
sys.modules['mutagen.mp3'].MP3 = MockMP3
MockEasyMP4Tags = type('EasyMP4Tags', (dict,), {'RegisterTextKey': staticmethod(lambda k, d: None)})
MockEasyMP4Tags.__module__ = 'mutagen.easymp4'
sys.modules['mutagen.easymp4'].EasyMP4Tags = MockEasyMP4Tags
sys.modules['mutagen.flac'].FLAC = MagicMock
sys.modules['mutagen.flac'].VCFLACDict = MagicMock
sys.modules['mutagen.mp4'].MP4 = MagicMock
sys.modules['mutagen.mp4'].MP4Tags = MagicMock
sys.modules['mutagen.mp4'].MP4FreeForm = MagicMock
sys.modules['mutagen.mp4'].MP4StreamInfoError = Exception
sys.modules['mutagen.oggopus'].OggOpus = MagicMock
sys.modules['mutagen.oggopus'].OggOpusVComment = MagicMock
sys.modules['mutagen.wave'].WAVE = MagicMock
sys.modules['mutagen.wave']._WaveID3 = MagicMock
sys.modules['mutagen.id3'].TXXX = MagicMock
sys.modules['mutagen.id3'].TextFrame = MagicMock
os.environ.setdefault('import_folder_path', '/tmp/import')
os.environ.setdefault('music_folder_path', '/tmp/music')
os.environ.setdefault('eps_folder_path', '/tmp/eps')
os.environ.setdefault('delimiter', '/')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_USER', 'user')
os.environ.setdefault('DB_PORT', '0')
os.environ.setdefault('DB_PASS', '')
os.environ.setdefault('DB_DB', 'db')
for mod_name in ['yt_dlp', 'yt_dlp.postprocessor', 'yt_dlp.utils']:
    m = types.ModuleType(mod_name)
    sys.modules[mod_name] = m
if 'yt_dlp' in sys.modules:
    sys.modules['yt_dlp'].YoutubeDL = MagicMock
if 'yt_dlp.postprocessor' in sys.modules:
    pp_mod = sys.modules['yt_dlp.postprocessor']

    class MockPostProcessor:

        def __init__(self, *args, **kwargs):
            pass
    pp_mod.PostProcessor = MockPostProcessor
    pp_mod.FFmpegMetadataPP = MockPostProcessor
    pp_mod.EmbedThumbnailPP = MockPostProcessor
for mod_name in ['markdown', 'dotenv', 'pymysql', 'pymysql.err', 'dbutils', 'dbutils.pooled_db']:
    # Always mock these to prevent real side effects during tests
    mock_mod = MagicMock()
    if mod_name == 'pymysql':
        mock_mod.err = MagicMock()
        mock_mod.err.OperationalError = type('OperationalError', (Exception,), {})
    if mod_name == 'pymysql.err':
        mock_mod.OperationalError = type('OperationalError', (Exception,), {})
        # Also ensure pymysql.err in sys.modules is consistent with pymysql.err attribute
        if 'pymysql' in sys.modules:
            sys.modules['pymysql'].err = mock_mod
    sys.modules[mod_name] = mock_mod
for mod_name in ['services.common.config_store', 'services.common.Helpers.NotificationService', 'services.common.Helpers.ProcessedFilesHelper']:
    # Always mock these to prevent real side effects during tests
    sys.modules[mod_name] = MagicMock()
if 'services.common.config_store' in sys.modules:
    mock_cs = sys.modules['services.common.config_store']
    if isinstance(mock_cs, MagicMock):
        mock_cs.ConfigStore.return_value.get_many.return_value = {'youtube_folder': '/tmp/youtube', 'youtube_archive': '/tmp/archive', 'soundcloud_folder': '/tmp/soundcloud', 'soundcloud_archive': '/tmp/archive', 'delimiter': '/'}
        mock_cs.ConfigStore.return_value.delimiter = '/'
if 'yt_dlp.utils' in sys.modules:
    sys.modules['yt_dlp.utils'].sanitize_filename = lambda x, **k: x
if 'dotenv' in sys.modules:
    sys.modules['dotenv'].load_dotenv = lambda *a, **k: None
if 'services.common.Helpers.NotificationService' in sys.modules:
    if not isinstance(sys.modules['services.common.Helpers.NotificationService'], MagicMock):
        sys.modules['services.common.Helpers.NotificationService'] = MagicMock()
    sys.modules['services.common.Helpers.NotificationService'].notification_service = MagicMock()
# Force mock Cache
cache_mod = types.ModuleType('services.common.Helpers.Cache')
cache_mod.databaseHelpers = {'library_artists': MagicMock(), 'rules_ignored_artists': MagicMock(), 'rules_genres': MagicMock(), 'rules_ignored_genres': MagicMock(), 'artistGenreHelper': MagicMock(), 'subgenreHelper': MagicMock(), 'rules_genre_backlog': MagicMock(), 'rules_label_genre': MagicMock(), 'rules_subgenre_hierarchy': MagicMock()}
sys.modules['services.common.Helpers.Cache'] = cache_mod
for helper_name in ['library_artists', 'rules_ignored_artists', 'rules_genres', 'rules_ignored_genres', 'rules_genre_backlog']:
    helper = cache_mod.databaseHelpers[helper_name]
    helper.get.side_effect = lambda x: x
    helper.get_corrected.side_effect = lambda x: x
    helper.get_corrected_or_exists.side_effect = lambda x: x
    helper.exists.return_value = False
    helper.get_all_values.return_value = []
    helper.get_all.return_value = []
for helper_name in ['artistGenreHelper', 'subgenreHelper', 'rules_label_genre', 'rules_subgenre_hierarchy']:
    if helper_name in cache_mod.databaseHelpers:
        helper = cache_mod.databaseHelpers[helper_name]
        helper.get.return_value = []
        helper.get.side_effect = None
cache_mod.databaseHelpers['rules_genres'].exists.return_value = True
# Force mock DatabaseConnector
db_conn_mod = types.ModuleType('services.common.Helpers.DatabaseConnector')

class MockDatabaseConnector:

    def connect(self):
        return MagicMock()
db_conn_mod.DatabaseConnector = MockDatabaseConnector
sys.modules['services.common.Helpers.DatabaseConnector'] = db_conn_mod

def setup_mocks():
    pass

def reset_database_helpers():
    if 'services.common.Helpers.NotificationService' in sys.modules:
        sys.modules['services.common.Helpers.NotificationService'].notification_service.reset_mock()
    helpers = sys.modules['services.common.Helpers.Cache'].databaseHelpers
    for h_name, h in helpers.items():
        if isinstance(h, MagicMock):
            h.reset_mock()
            h.exists.return_value = False
            h.get_all_values.return_value = []
            h.get_all.return_value = []
            if h_name in ['library_artists', 'rules_ignored_artists', 'rules_genres', 'rules_ignored_genres', 'rules_genre_backlog']:
                h.get.side_effect = lambda x: x
                h.get_corrected.side_effect = lambda x: x
                h.get_corrected_or_exists.side_effect = lambda x: x
            else:
                h.get.return_value = []
                h.get.side_effect = None
    helpers['rules_genres'].exists.return_value = True