from enum import Enum
from typing import Final

# Constants
ARTIST_REGEX: Final = "\s(&|and|feat\.?|featuring|features|ft\.?|presenting|X|pres\.?|versus|vs\.?)\s"

# noinspection SpellCheckingInspection
ALBUM_ARTIST: Final = "albumartist"
ARTIST: Final = "artist"
BPM: Final = "bpm"
# noinspection SpellCheckingInspection
CATALOG_NUMBER: Final = "catalognumber"
COPYRIGHT: Final = "copyright"
DATE: Final = "date"
GENRE: Final = "genre"
PARSED: Final = "parsed"
PUBLISHER: Final = "publisher"
TITLE: Final = "title"

MP4Tags = {
    ALBUM_ARTIST: 'TALB',
    ARTIST: '\xa9ART',
    CATALOG_NUMBER: 'CATA',
    COPYRIGHT: 'cprt',
    DATE: '\xa9DAY',
    GENRE: '\xa9gen',
    PUBLISHER: 'PUBL',
}

WAVTags = {
    ALBUM_ARTIST: 'ALBU',
    ARTIST: 'TPE1',
    CATALOG_NUMBER: 'CATA',
    COPYRIGHT: 'cprt',
    DATE: 'TDRC',
    GENRE: 'TCON',
    PUBLISHER: 'PUBLISHER',
    TITLE: 'TIT2',
}


# Enumerations
class FormatEnum(Enum):
    NONE = 0
    RECAPITALIZE = 1


class SongTypeEnum(Enum):
    NONE = 0
    LABEL = 1
    YOUTUBE = 2
    SOUNDCLOUD = 3
    GENERIC = 4


class MusicFileType(Enum):
    NONE = 0
    MP3 = 1
    FLAC = 2
    WAV = 3
    M4A = 4
