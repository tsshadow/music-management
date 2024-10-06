from enum import Enum
from typing import Final

# Constants
ARTIST_REGEX: Final = "\s(&|and|feat\.?|featuring|features|ft\.?|presenting|X|pres\.?|versus|vs\.?)\s"

# noinspection SpellCheckingInspection
CATALOG_NUMBER: Final = "CATALOGNUMBER"
TITLE: Final = ""
PUBLISHER: Final = "PUBLISHER"
PUBLISHER_OLD: Final = "PUBLISHER_OLD"
DATE: Final = "DATE"
BPM: Final = "BPM"
COPYRIGHT: Final = "COPYRIGHT"
GENRE: Final = "GENRE"
ARTIST: Final = "ARTIST"
# noinspection SpellCheckingInspection
ALBUM_ARTIST: Final = "ALBUMARTIST"
PARSED: Final = "PARSED"

MP4Tags = {
    ALBUM_ARTIST: 'TALB',
    GENRE: '\xa9gen',
    PUBLISHER: 'PUBL',
    ARTIST: '\xa9ART',
    DATE: '\xa9DAY',
    COPYRIGHT: 'cprt',
    CATALOG_NUMBER: 'CATA'
}

WAVTags = {
    TITLE: 'TIT2',
    ARTIST: 'TPE1',
    ALBUM_ARTIST: 'ALBU',
    GENRE: 'TCON',
    PUBLISHER: 'PUBLISHER',
    DATE: 'TDRC',
    COPYRIGHT: 'cprt',
    CATALOG_NUMBER: 'CATA'
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
