"""Opt-in stand-ins for the libraries and helpers a unit test must not reach for real.

This module used to replace mutagen, pymysql, yt_dlp, config_store, Cache and a dozen
more in ``sys.modules`` the moment ``services/conftest.py`` loaded it, for every test in
the session. A test that needed the real library got a stub, and a stub value could leak
into real output (bug report 082: ``<MagicMock ...>`` in an ntfy push). See bug report 085.

Now nothing is installed on import. A test module asks for exactly the stubs it relies
on, with a module-level marker::

    pytestmark = pytest.mark.mock_base('mutagen', 'Cache')

``services/tests/mock_base_plugin.py`` reads that marker straight from the file's source
(before the module is imported, since most of these stubs have to be in place while the
module's own imports run), and installs the requested stubs only while that module is
being imported and while its tests run. Everything imported under the stubs -- the
project modules above all, which hold references to the stub classes -- is lifted out of
``sys.modules`` again afterwards, so a later test that asked for nothing imports the real
thing. Modules that ask for the same set of stubs share one such "world", the way every
test used to share the single session-wide one.

Each entry in ``STUB_BUILDERS`` is one stub name a marker may list; a builder returns the
``sys.modules`` entries that name stands for. Builders run once per world, so every world
gets fresh stub objects.
"""

import contextlib
import os
import sys
import types
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

# The attribute every stub module carries, so a leak check can tell a stub from the real
# module without importing anything. A MagicMock raises AttributeError for dunder names,
# which is why the leak check also tests isinstance(..., MagicMock).
STUB_FLAG = '__mock_base_stub__'

# Environment defaults the code under test reads at import time (config paths, the DB
# settings DatabaseConnector would otherwise build a connection string from). These are
# plain environment variables, not modules, and nothing can leak through them: they are
# set once, with setdefault, for the whole session, as before.
ENV_DEFAULTS = {
    'import_folder_path': '/tmp/import',
    'music_folder_path': '/mnt/music',
    'eps_folder_path': '/tmp/eps',
    'delimiter': '/',
    'DB_HOST': 'localhost',
    'DB_USER': 'user',
    'DB_PORT': '0',
    'DB_PASS': '',
    'DB_DB': 'db',
}


def apply_env_defaults():
    """Set the environment defaults above, never overriding a value that is already set."""
    for key, value in ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


def _module(name: str) -> Any:
    """Create an empty stub module flagged as coming from mock_base.

    Typed as Any: the builders assign the stubbed attributes onto it one by one.
    """
    mod = types.ModuleType(name)
    setattr(mod, STUB_FLAG, True)
    return mod


def _mock_module(name: str) -> MagicMock:
    """Create a MagicMock that stands in for a whole module."""
    mod = MagicMock(name=name)
    mod.__name__ = name
    return mod


# --- mutagen -------------------------------------------------------------------------


class MockPairIterDict(dict):
    """Mutagen's Vorbis-comment containers iterate as (key, value) pairs, not as keys."""

    def __iter__(self):
        return iter(self.items())


class MockMP4FreeForm(bytes):
    """MP4FreeForm is a bytes subclass; the tagger relies on .decode()."""

    __module__ = 'mutagen.mp4'


class MockTextFrame:
    """Stand-in for an ID3 text frame (TPE1, TIT2, ...): what matters is `.text`."""

    __module__ = 'mutagen.id3'

    def __init__(self, encoding=3, text=None):
        self.encoding = encoding
        self.text = text if text is not None else []


def _build_mutagen() -> dict:
    """Build the mutagen package: tag containers are dicts, files carry a 180s length."""
    mutagen_mod = _module('mutagen')
    mutagen_mod.MutagenError = Exception
    modules = {'mutagen': mutagen_mod}
    for sub in ['easyid3', 'mp3', 'easymp4', 'flac', 'mp4', 'oggopus', 'wave', 'id3']:
        sub_mod = _module(f'mutagen.{sub}')
        modules[f'mutagen.{sub}'] = sub_mod
        setattr(mutagen_mod, sub, sub_mod)

    easy_id3 = type(
        'EasyID3', (dict,), {'save': lambda self, *a, **k: None, 'RegisterTXXXKey': staticmethod(lambda k, d: None)}
    )
    easy_id3.__module__ = 'mutagen.easyid3'
    modules['mutagen.easyid3'].EasyID3 = easy_id3

    def _mp3_init(self, *_args, **_kwargs):
        dict.__init__(self)
        self.tags = easy_id3()
        self.info = MagicMock(length=180)

    mp3 = type('MP3', (dict,), {'__init__': _mp3_init, 'save': lambda self, *a, **k: None})
    mp3.__module__ = 'mutagen.mp3'
    modules['mutagen.mp3'].MP3 = mp3

    easy_mp4_tags = type('EasyMP4Tags', (dict,), {'RegisterTextKey': staticmethod(lambda k, d: None)})
    easy_mp4_tags.__module__ = 'mutagen.easymp4'
    modules['mutagen.easymp4'].EasyMP4Tags = easy_mp4_tags

    vc_flac_dict = type('VCFLACDict', (MockPairIterDict,), {'__module__': 'mutagen.flac'})
    ogg_opus_vcomment = type('OggOpusVComment', (MockPairIterDict,), {'__module__': 'mutagen.oggopus'})
    # ID3-backed and MP4 containers iterate as plain keys, so a dict subclass is enough.
    wave_id3 = type('_WaveID3', (dict,), {'__module__': 'mutagen.wave'})
    mp4_tags = type('MP4Tags', (dict,), {'__module__': 'mutagen.mp4'})

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
            self.tags = mp4_tags()
            self.info = MagicMock(length=180)

        def save(self, *_args, **_kwargs):
            """Saving is a no-op: nothing is written to disk."""

    modules['mutagen.flac'].FLAC = MagicMock
    modules['mutagen.flac'].VCFLACDict = vc_flac_dict
    modules['mutagen.mp4'].MP4 = MockMP4
    modules['mutagen.mp4'].MP4Tags = mp4_tags
    modules['mutagen.mp4'].MP4FreeForm = MockMP4FreeForm
    modules['mutagen.mp4'].MP4StreamInfoError = Exception
    modules['mutagen.oggopus'].OggOpus = MagicMock
    modules['mutagen.oggopus'].OggOpusVComment = ogg_opus_vcomment
    modules['mutagen.wave'].WAVE = MagicMock
    modules['mutagen.wave']._WaveID3 = wave_id3
    modules['mutagen.id3'].TXXX = MagicMock
    modules['mutagen.id3'].TextFrame = MockTextFrame
    for frame_name in ['TPE1', 'TPE2', 'TPE4', 'TIT2', 'TALB', 'TCON', 'TDRC', 'TRCK', 'TBPM', 'TPUB', 'TCOP']:
        setattr(modules['mutagen.id3'], frame_name, type(frame_name, (MockTextFrame,), {'__module__': 'mutagen.id3'}))
    return modules


# --- archive, audio-analysis and ml-analyzer dependencies ----------------------------


def _build_patoolib() -> dict:
    """patoolib shells out to real archive tools; the importer only needs PatoolError."""
    patoolib_mod = _module('patoolib')
    util_mod = _module('patoolib.util')
    util_mod.PatoolError = type('PatoolError', (Exception,), {'__module__': 'patoolib.util'})
    patoolib_mod.util = util_mod
    patoolib_mod.extract_archive = MagicMock()
    return {'patoolib': patoolib_mod, 'patoolib.util': util_mod}


def _build_librosa() -> dict:
    """librosa drags in numba, which is slow and version-sensitive; BPM is asserted via mocks."""
    librosa_mod = _module('librosa')
    beat_mod = _module('librosa.beat')
    beat_mod.beat_track = lambda *a, **k: (0, None)
    librosa_mod.beat = beat_mod
    librosa_mod.load = lambda *a, **k: ([], 0)
    return {'librosa': librosa_mod, 'librosa.beat': beat_mod}


def _build_sqlalchemy() -> dict:
    """The ml-analyzer's SQLAlchemy is not in the root requirements; its logic is what is tested."""
    modules = {'sqlalchemy': _mock_module('sqlalchemy')}
    for sub in ['dialects', 'dialects.mysql', 'orm', 'exc']:
        modules[f'sqlalchemy.{sub}'] = _mock_module(f'sqlalchemy.{sub}')
    modules['sqlalchemy'].dialects = modules['sqlalchemy.dialects']
    modules['sqlalchemy.dialects'].mysql = modules['sqlalchemy.dialects.mysql']
    return modules


def _build_plain_mock(*names: str) -> Callable[[], dict]:
    """Return a builder that stands a MagicMock in for each of the given module names."""

    def build() -> dict:
        return {name: _mock_module(name) for name in names}

    return build


def _build_tqdm() -> dict:
    """tqdm(iterable) has to keep iterating, or every progress-wrapped loop would run zero times."""
    tqdm_mod = _mock_module('tqdm')
    tqdm_mod.tqdm = lambda iterable=(), *a, **k: iterable
    return {'tqdm': tqdm_mod}


class _NdarrayStub:
    """Stands in for numpy.ndarray so `isinstance(x, numpy.ndarray)` stays legal.

    hypothesis runs exactly that check on every generated value when numpy is
    loaded, and a MagicMock attribute is not a type.
    """


def _build_numpy() -> dict:
    """numpy for the ml-analyzer: its signal maths is never asserted on, its branching is."""
    numpy_mod = _mock_module('numpy')
    numpy_mod.ndarray = _NdarrayStub
    # hypothesis seeds numpy's global RNG whenever 'numpy' is in sys.modules, with a
    # plain `import numpy.random` -- which fails on a MagicMock unless the submodule is
    # registered next to it.
    return {'numpy': numpy_mod, 'numpy.random': numpy_mod.random}


# --- ingestion and infrastructure libraries ------------------------------------------


def _build_yt_dlp() -> dict:
    """yt_dlp with a MagicMock YoutubeDL, inert post-processors and an identity sanitizer."""
    modules = {name: _module(name) for name in ['yt_dlp', 'yt_dlp.postprocessor', 'yt_dlp.utils']}
    modules['yt_dlp'].YoutubeDL = MagicMock
    modules['yt_dlp'].postprocessor = modules['yt_dlp.postprocessor']
    modules['yt_dlp'].utils = modules['yt_dlp.utils']

    class MockPostProcessor:
        """A post-processor that accepts any arguments and does nothing."""

        def __init__(self, *args, **kwargs):
            pass

    for name in ['PostProcessor', 'FFmpegMetadataPP', 'EmbedThumbnailPP']:
        setattr(modules['yt_dlp.postprocessor'], name, MockPostProcessor)
    modules['yt_dlp.utils'].sanitize_filename = lambda x, **k: x
    return modules


def _build_dotenv() -> dict:
    """dotenv whose load_dotenv never reads a developer's .env."""
    mod = _mock_module('dotenv')
    mod.load_dotenv = lambda *a, **k: None
    return {'dotenv': mod}


def _build_pymysql() -> dict:
    """pymysql as a MagicMock, with a real OperationalError class so `except` clauses work."""
    pymysql_mod = _mock_module('pymysql')
    err_mod = _mock_module('pymysql.err')
    err_mod.OperationalError = type('OperationalError', (Exception,), {})
    cursors_mod = _mock_module('pymysql.cursors')
    # `import pymysql.cursors` needs both the sys.modules entry and the attribute.
    pymysql_mod.err = err_mod
    pymysql_mod.cursors = cursors_mod
    return {'pymysql': pymysql_mod, 'pymysql.err': err_mod, 'pymysql.cursors': cursors_mod}


def _build_config_store() -> dict:
    """A ConfigStore whose get_many answers the download folders and nothing reaches MariaDB."""
    mock_cs = _mock_module('services.common.config_store')
    mock_cs.ConfigStore.return_value.get_many.return_value = {
        'youtube_folder': '/tmp/youtube',
        'youtube_archive': '/tmp/archive',
        'soundcloud_folder': '/tmp/soundcloud',
        'soundcloud_archive': '/tmp/archive',
        'delimiter': '/',
    }
    mock_cs.ConfigStore.return_value.delimiter = '/'
    # `credential()` is a real function on the real module; a MagicMock in its place
    # returns a truthy MagicMock for every key, which makes every provider look
    # configured. Keep the environment half of its behaviour, drop the store half.
    mock_cs.credential = lambda config_key, env_name: os.getenv(env_name) or None
    return {'services.common.config_store': mock_cs}


class MockDatabaseConnector:
    """A DatabaseConnector whose connections are MagicMocks, so no test reaches MariaDB."""

    def connect(self):
        """Return a fresh MagicMock connection."""
        return MagicMock()

    @contextlib.contextmanager
    def connection(self):
        """Yield a connection and close it afterwards, like the real context manager."""
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()


def _build_database_connector() -> dict:
    """The DatabaseConnector module with MockDatabaseConnector in place of the real class."""
    mod = _module('services.common.Helpers.DatabaseConnector')
    mod.DatabaseConnector = MockDatabaseConnector
    return {'services.common.Helpers.DatabaseConnector': mod}


# The Cache helpers that echo their input: an artist or genre is "corrected" to itself.
_ECHO_HELPERS = [
    'library_artists',
    'rules_ignored_artists',
    'rules_genres',
    'rules_ignored_genres',
    'rules_genre_backlog',
]
# The Cache helpers that return an empty list of rows.
_LIST_HELPERS = [
    'artistGenreHelper',
    'subgenreHelper',
    'rules_label_genre',
    'rules_subgenre_hierarchy',
    'sceneGroupDateFormatHelper',
    'labelGenreHelper',
]


def _configure_echo_helper(helper: MagicMock) -> None:
    """Make a MagicMock helper answer every lookup with its own argument."""
    helper.get.side_effect = lambda x: x
    helper.get_corrected.side_effect = lambda x: x
    helper.get_corrected_or_exists.side_effect = lambda x: x
    helper.exists.return_value = False
    helper.get_all_values.return_value = []
    helper.get_all.return_value = []


def _build_cache() -> dict:
    """The Cache module: MagicMock helpers, plus real in-memory genre/festival/podcast helpers.

    Imports GenreRulesHelper, FestivalHelper and PodcastHelper, so it runs after the
    other stubs of the same world are in sys.modules and those imports see them.
    """
    cache_mod = _module('services.common.Helpers.Cache')
    cache_mod.databaseHelpers = {name: MagicMock() for name in _ECHO_HELPERS + _LIST_HELPERS}
    # The curation endpoints call Cache.reload after every rule write so the running
    # tagger stops answering from the map it preloaded at import. The real function
    # lives in Cache.py, which this module replaces, so it has to be stubbed here.
    cache_mod.reload = MagicMock(return_value=[])
    for name in _ECHO_HELPERS:
        _configure_echo_helper(cache_mod.databaseHelpers[name])
    for name in _LIST_HELPERS:
        cache_mod.databaseHelpers[name].get.return_value = []
    cache_mod.databaseHelpers['rules_genres'].exists.return_value = True
    # These must import under the world's stubs, hence inside the function.
    # pylint: disable=import-outside-toplevel
    from services.common.Helpers.ChannelLinkHelper import ChannelLinkHelper
    from services.common.Helpers.FestivalHelper import FestivalHelper
    from services.common.Helpers.GenreRulesHelper import GenreRulesHelper
    from services.common.Helpers.PodcastHelper import PodcastHelper

    # The genre rules helper is a real object holding in-memory rows: a MagicMock would
    # hand every rule a truthy decision and hide what the rule actually does. Tests give
    # it the rows they need via set_rows().
    cache_mod.databaseHelpers['genre_rules'] = GenreRulesHelper(preload=False, rows=[])
    cache_mod.databaseHelpers['genre_rules'].record_unknown = MagicMock()
    # Same reasoning: a MagicMock would report a festival match for every file.
    cache_mod.databaseHelpers['festivalHelper'] = FestivalHelper(preload=False)
    # Same again for shows: a MagicMock would claim every file is an episode of something.
    cache_mod.databaseHelpers['podcastHelper'] = PodcastHelper(preload=False)
    # And for channel links: a MagicMock would link every download to a label.
    cache_mod.databaseHelpers['channelLinkHelper'] = ChannelLinkHelper(preload=False)
    return {'services.common.Helpers.Cache': cache_mod}


# Every name a `mock_base` marker may list, in the order a world builds them. Order
# matters only for Cache, whose builder imports real helpers that must see the rest.
STUB_BUILDERS: dict[str, Callable[[], dict]] = {
    'mutagen': _build_mutagen,
    'patoolib': _build_patoolib,
    'librosa': _build_librosa,
    'sqlalchemy': _build_sqlalchemy,
    'pandas': _build_plain_mock('pandas'),
    'joblib': _build_plain_mock('joblib'),
    'tqdm': _build_tqdm,
    'sklearn': _build_plain_mock(
        'sklearn', 'sklearn.ensemble', 'sklearn.model_selection', 'sklearn.preprocessing', 'sklearn.metrics'
    ),
    'numpy': _build_numpy,
    'yt_dlp': _build_yt_dlp,
    'markdown': _build_plain_mock('markdown'),
    'dotenv': _build_dotenv,
    'pymysql': _build_pymysql,
    'dbutils': _build_plain_mock('dbutils', 'dbutils.pooled_db'),
    'config_store': _build_config_store,
    'ProcessedFilesHelper': _build_plain_mock('services.common.Helpers.ProcessedFilesHelper'),
    'DatabaseConnector': _build_database_connector,
    'Cache': _build_cache,
}

# The sys.modules names each stub owns. A name also owns everything below it (a real
# `mutagen._util` must never sit next to a stubbed `mutagen`). The leak check in
# tests/ci/ walks exactly this list.
STUB_MODULE_NAMES: dict[str, tuple[str, ...]] = {
    'mutagen': ('mutagen',),
    'patoolib': ('patoolib',),
    'librosa': ('librosa',),
    'sqlalchemy': ('sqlalchemy',),
    'pandas': ('pandas',),
    'joblib': ('joblib',),
    'tqdm': ('tqdm',),
    'sklearn': ('sklearn',),
    'numpy': ('numpy',),
    'yt_dlp': ('yt_dlp',),
    'markdown': ('markdown',),
    'dotenv': ('dotenv',),
    'pymysql': ('pymysql',),
    'dbutils': ('dbutils',),
    'config_store': ('services.common.config_store',),
    'ProcessedFilesHelper': ('services.common.Helpers.ProcessedFilesHelper',),
    'DatabaseConnector': ('services.common.Helpers.DatabaseConnector',),
    'Cache': ('services.common.Helpers.Cache',),
}


def owned_by_stub(module_name: str, stub_names) -> bool:
    """True when a sys.modules key is, or sits below, a module one of the stubs replaces."""
    for stub in stub_names:
        for owned in STUB_MODULE_NAMES[stub]:
            if module_name == owned or module_name.startswith(owned + '.'):
                return True
    return False


def is_stub(module) -> bool:
    """True when a sys.modules value is a mock_base stub (or any MagicMock standing in for one)."""
    return isinstance(module, MagicMock) or bool(getattr(module, STUB_FLAG, False))


def build_stubs(names) -> dict:
    """Build the sys.modules entries for the given stub names, installing each as it is built.

    Installing as it goes is what lets a later builder (Cache) import code that sees the
    earlier stubs. Raises KeyError for a name that is not in STUB_BUILDERS.
    """
    unknown = sorted(set(names) - set(STUB_BUILDERS))
    if unknown:
        raise KeyError(f'unknown mock_base stub(s) {unknown}; known: {sorted(STUB_BUILDERS)}')
    built: dict = {}
    for name, builder in STUB_BUILDERS.items():
        if name in names:
            modules = builder()
            sys.modules.update(modules)
            built.update(modules)
    return built


def reset_database_helpers():
    """Put the Cache stub's helpers back into their default answers between tests.

    Only meaningful in a module that asked for the 'Cache' stub.
    """
    helpers = sys.modules['services.common.Helpers.Cache'].databaseHelpers
    for h_name, h in helpers.items():
        if isinstance(h, MagicMock):
            h.reset_mock()
            h.exists.return_value = False
            h.get_all_values.return_value = []
            h.get_all.return_value = []
            if h_name in _ECHO_HELPERS:
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
    helpers['podcastHelper'].set_shows([])
    helpers['channelLinkHelper'].set_links([])
