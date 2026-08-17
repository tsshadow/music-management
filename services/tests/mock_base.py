import contextlib
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



class MockPairIterDict(dict):
    """Mutagen's Vorbis-comment containers iterate as (key, value) pairs, not as keys."""

    def __iter__(self):
        return iter(self.items())


MockVCFLACDict = type('VCFLACDict', (MockPairIterDict,), {'__module__': 'mutagen.flac'})
MockOggOpusVComment = type('OggOpusVComment', (MockPairIterDict,), {'__module__': 'mutagen.oggopus'})
# ID3-backed and MP4 containers iterate as plain keys, so a dict subclass is enough.
MockWaveID3 = type('_WaveID3', (dict,), {'__module__': 'mutagen.wave'})
MockMP4Tags = type('MP4Tags', (dict,), {'__module__': 'mutagen.mp4'})


class MockMP4FreeForm(bytes):
    """MP4FreeForm is a bytes subclass; the tagger relies on .decode()."""
    __module__ = 'mutagen.mp4'


class MockTextFrame:
    """Stand-in for an ID3 text frame (TPE1, TIT2, ...): what matters is `.text`."""
    __module__ = 'mutagen.id3'

    def __init__(self, encoding=3, text=None):
        self.encoding = encoding
        self.text = text if text is not None else []


class MockMP4(dict):
    """An m4a whose tags are a real MP4Tags dict, the way MockMP3 does for mp3.

    Subclasses dict because mutagen's FileType is itself mapping-like: the tagger
    reads `music_file.get(...)` and `music_file.pop(...)` straight off it.

    A bare MagicMock hands TagCollection an attribute that is neither None nor an
    MP4Tags, so every m4a test had to patch mutagen out again and could never
    assert on what the tagger actually wrote. YouTube downloads are m4a, so the
    format that carries most of the library was the one with no usable fixture.
    """
    __module__ = 'mutagen.mp4'

    def __init__(self, *_args, **_kwargs):
        super().__init__()
        self.tags = MockMP4Tags()
        self.info = MagicMock(length=180)

    def save(self, *_args, **_kwargs):
        pass


sys.modules['mutagen.flac'].FLAC = MagicMock
sys.modules['mutagen.flac'].VCFLACDict = MockVCFLACDict
sys.modules['mutagen.mp4'].MP4 = MockMP4
sys.modules['mutagen.mp4'].MP4Tags = MockMP4Tags
sys.modules['mutagen.mp4'].MP4FreeForm = MockMP4FreeForm
sys.modules['mutagen.mp4'].MP4StreamInfoError = Exception
sys.modules['mutagen.oggopus'].OggOpus = MagicMock
sys.modules['mutagen.oggopus'].OggOpusVComment = MockOggOpusVComment
sys.modules['mutagen.wave'].WAVE = MagicMock
sys.modules['mutagen.wave']._WaveID3 = MockWaveID3
sys.modules['mutagen.id3'].TXXX = MagicMock
sys.modules['mutagen.id3'].TextFrame = MockTextFrame
for _frame_name in ['TPE1', 'TPE2', 'TPE4', 'TIT2', 'TALB', 'TCON', 'TDRC', 'TRCK', 'TBPM', 'TPUB', 'TCOP']:
    setattr(sys.modules['mutagen.id3'], _frame_name, type(_frame_name, (MockTextFrame,), {'__module__': 'mutagen.id3'}))
os.environ.setdefault('import_folder_path', '/tmp/import')
os.environ.setdefault('music_folder_path', '/mnt/music')
os.environ.setdefault('eps_folder_path', '/tmp/eps')
os.environ.setdefault('delimiter', '/')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_USER', 'user')
os.environ.setdefault('DB_PORT', '0')
os.environ.setdefault('DB_PASS', '')
os.environ.setdefault('DB_DB', 'db')
# patoolib shells out to real archive tools; the importer only ever needs the module
# to exist and to expose PatoolError as a catchable exception class.
patoolib_mod = types.ModuleType('patoolib')
patoolib_util_mod = types.ModuleType('patoolib.util')
patoolib_util_mod.PatoolError = type('PatoolError', (Exception,), {'__module__': 'patoolib.util'})
patoolib_mod.util = patoolib_util_mod
patoolib_mod.extract_archive = MagicMock()
sys.modules['patoolib'] = patoolib_mod
sys.modules['patoolib.util'] = patoolib_util_mod
# librosa drags in numba, which is both slow and version-sensitive. BPM analysis is
# only ever asserted through mocked return values, so a stub is enough.
librosa_mod = types.ModuleType('librosa')
librosa_beat_mod = types.ModuleType('librosa.beat')
librosa_beat_mod.beat_track = lambda *a, **k: (0, None)
librosa_mod.beat = librosa_beat_mod
librosa_mod.load = lambda *a, **k: ([], 0)
sys.modules['librosa'] = librosa_mod
sys.modules['librosa.beat'] = librosa_beat_mod
# The ml-analyzer's dependencies (services/ml-analyzer/requirements.txt) are not in
# the repository-root requirements.txt, and CI does not pip-install anything before
# running this suite -- it uses what the runner already has. Stubbing them here is
# the same trade already made for librosa and yt_dlp above: the analyzer's own logic
# is what these tests assert on, never SQLAlchemy's or scikit-learn's behaviour.
sqlalchemy_mod = MagicMock()
sqlalchemy_mod.__name__ = 'sqlalchemy'
sys.modules['sqlalchemy'] = sqlalchemy_mod
for _sub in ['dialects', 'dialects.mysql', 'orm', 'exc']:
    sys.modules[f'sqlalchemy.{_sub}'] = MagicMock()
sqlalchemy_mod.dialects = sys.modules['sqlalchemy.dialects']
sys.modules['sqlalchemy.dialects'].mysql = sys.modules['sqlalchemy.dialects.mysql']
for mod_name in ['pandas', 'joblib', 'tqdm', 'sklearn', 'sklearn.ensemble',
                 'sklearn.model_selection', 'sklearn.preprocessing', 'sklearn.metrics']:
    sys.modules[mod_name] = MagicMock()
# numpy is in the root requirements, but only the ml-analyzer imports it, and a
# stub keeps these tests runnable on a machine that has not installed it. The raw
# signal maths it backs is deliberately not asserted on; the analyzer's own
# branching is.
sys.modules['numpy'] = MagicMock()
# tqdm(iterable) has to keep iterating, or every progress-wrapped loop would run zero times.
sys.modules['tqdm'].tqdm = lambda iterable=(), *a, **k: iterable

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
for mod_name in ['markdown', 'dotenv', 'pymysql', 'pymysql.err', 'pymysql.cursors', 'dbutils', 'dbutils.pooled_db']:
    # Always mock these to prevent real side effects during tests
    mock_mod = MagicMock()
    if mod_name == 'pymysql':
        mock_mod.err = MagicMock()
        mock_mod.err.OperationalError = type('OperationalError', (Exception,), {})
    # `import pymysql.cursors` needs both the sys.modules entry and the attribute.
    if mod_name == 'pymysql.cursors' and 'pymysql' in sys.modules:
        sys.modules['pymysql'].cursors = mock_mod
    if mod_name == 'pymysql.err':
        mock_mod.OperationalError = type('OperationalError', (Exception,), {})
        # Also ensure pymysql.err in sys.modules is consistent with pymysql.err attribute
        if 'pymysql' in sys.modules:
            sys.modules['pymysql'].err = mock_mod
    sys.modules[mod_name] = mock_mod
for mod_name in ['services.common.config_store', 'services.common.Helpers.ProcessedFilesHelper']:
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
# Force mock Cache
cache_mod = types.ModuleType('services.common.Helpers.Cache')
cache_mod.databaseHelpers = {'library_artists': MagicMock(), 'rules_ignored_artists': MagicMock(), 'rules_genres': MagicMock(), 'rules_ignored_genres': MagicMock(), 'artistGenreHelper': MagicMock(), 'subgenreHelper': MagicMock(), 'rules_genre_backlog': MagicMock(), 'rules_label_genre': MagicMock(), 'rules_subgenre_hierarchy': MagicMock(), 'sceneGroupDateFormatHelper': MagicMock()}
sys.modules['services.common.Helpers.Cache'] = cache_mod
for helper_name in ['library_artists', 'rules_ignored_artists', 'rules_genres', 'rules_ignored_genres', 'rules_genre_backlog']:
    helper = cache_mod.databaseHelpers[helper_name]
    helper.get.side_effect = lambda x: x
    helper.get_corrected.side_effect = lambda x: x
    helper.get_corrected_or_exists.side_effect = lambda x: x
    helper.exists.return_value = False
    helper.get_all_values.return_value = []
    helper.get_all.return_value = []
for helper_name in ['artistGenreHelper', 'subgenreHelper', 'rules_label_genre', 'rules_subgenre_hierarchy', 'sceneGroupDateFormatHelper']:
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

    @contextlib.contextmanager
    def connection(self):
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()
db_conn_mod.DatabaseConnector = MockDatabaseConnector
sys.modules['services.common.Helpers.DatabaseConnector'] = db_conn_mod
# The genre rules helper is a real object holding in-memory rows: a MagicMock would
# hand every rule a truthy decision and hide what the rule actually does. Tests give
# it the rows they need via set_rows().
from services.common.Helpers.GenreRulesHelper import GenreRulesHelper

cache_mod.databaseHelpers['genre_rules'] = GenreRulesHelper(preload=False, rows=[])
cache_mod.databaseHelpers['genre_rules'].record_unknown = MagicMock()
# Same reasoning as genre_rules: a MagicMock would report a festival match for every
# file, so tests get a real helper with no festivals in it and fill it when they mean to.
from services.common.Helpers.FestivalHelper import FestivalHelper

cache_mod.databaseHelpers['festivalHelper'] = FestivalHelper(preload=False)

def setup_mocks():
    pass

def reset_database_helpers():
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
    helpers['genre_rules'].set_rows([])
    helpers['genre_rules'].record_unknown.reset_mock()
    helpers['festivalHelper'].set_festivals([])
