import sys
import types

# Stub mutagen modules with minimal classes used in tests
if 'mutagen' not in sys.modules:
    mutagen = types.ModuleType('mutagen')
    mutagen.easyid3 = types.ModuleType('mutagen.easyid3')
    class EasyID3(dict):
        pass
    mutagen.easyid3.EasyID3 = EasyID3

    mutagen.flac = types.ModuleType('mutagen.flac')
    class VCFLACDict(dict):
        def __iter__(self):
            for k, v in dict.items(self):
                yield (k, v)
    class FLAC:
        def __init__(self, *a, **k):
            self.tags = VCFLACDict()
    mutagen.flac.VCFLACDict = VCFLACDict
    mutagen.flac.FLAC = FLAC

    mutagen.wave = types.ModuleType('mutagen.wave')
    class _WaveID3(dict):
        def items(self):
            return dict.items(self)
    class WAVE:
        def __init__(self, *a, **k):
            self.tags = _WaveID3()
    mutagen.wave._WaveID3 = _WaveID3
    mutagen.wave.WAVE = WAVE

    mutagen.mp4 = types.ModuleType('mutagen.mp4')
    class MP4Tags(dict):
        pass
    class MP4FreeForm(bytes):
        pass
    mutagen.mp4.MP4Tags = MP4Tags
    mutagen.mp4.MP4FreeForm = MP4FreeForm

    mutagen.id3 = types.ModuleType('mutagen.id3')
    class TPE1:
        def __init__(self, encoding=3, text=None):
            self.encoding = encoding
            self.text = text or []
    class ID3Tags(dict):
        pass
    class MP3:
        def __init__(self, *a, **k):
            self.tags = ID3Tags()
    class MP4:
        def __init__(self, *a, **k):
            self.tags = MP4Tags()
    mutagen.mp4.MP4 = MP4
    class MP4StreamInfoError(Exception):
            pass
    mutagen.id3.TPE1 = TPE1
    mutagen.id3.ID3Tags = ID3Tags
    mutagen.mp3 = types.ModuleType('mutagen.mp3')
    mutagen.mp3.MP3 = MP3
    mutagen.mp4.MP4StreamInfoError = MP4StreamInfoError

    sys.modules['mutagen'] = mutagen
    sys.modules['mutagen.easyid3'] = mutagen.easyid3
    sys.modules['mutagen.flac'] = mutagen.flac
    sys.modules['mutagen.wave'] = mutagen.wave
    sys.modules['mutagen.mp4'] = mutagen.mp4
    sys.modules['mutagen.mp3'] = mutagen.mp3
    sys.modules['mutagen.id3'] = mutagen.id3

# Stub pymysql
if 'pymysql' not in sys.modules:
    pymysql = types.ModuleType('pymysql')
    sys.modules['pymysql'] = pymysql

# Stub librosa used in BPM analysis tests
if 'librosa' not in sys.modules:
    librosa = types.ModuleType('librosa')
    def load(*a, **k):
        return [], 0
    librosa.load = load
    beat_mod = types.ModuleType('librosa.beat')
    def beat_track(*a, **k):
        return 0, None
    beat_mod.beat_track = beat_track
    librosa.beat = beat_mod
    sys.modules['librosa'] = librosa
    sys.modules['librosa.beat'] = beat_mod

if 'dotenv' not in sys.modules:
    dotenv = types.ModuleType('dotenv')
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules['dotenv'] = dotenv

if 'data.settings' not in sys.modules:
    settings_mod = types.ModuleType('data.settings')
    class Settings:
        def __init__(self):
            self.debug = "True"
            self.rescan = "True"
            self.dryrun = "False"
            self.import_folder_path = ""
            self.eps_folder_path = ""
            self.music_folder_path = ""
            self.delimiter = "/"
    settings_mod.Settings = Settings
    sys.modules['data.settings'] = settings_mod

