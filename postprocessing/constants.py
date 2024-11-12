from enum import Enum
from typing import Final

# Constants
ARTIST_REGEX: Final = "\s(&|aka|Aka|AKA|and|And|b2b|B2B|B2b|b3b|B3b|B3B|feat\.?|Feat\.?|featuring|Featuring|features|Features|ft|Ft\.?|ft\.?|invite|Invite|invites|Invites|pres\.?|Pres\.?|presenting|Presenting|versus|Versus|vs\.?|Vs\.?|VS\.?|with|With|x|X)\s"

# noinspection SpellCheckingInspection
ALBUM_ARTIST: Final = "albumartist"
ARTIST: Final = "artist"
ALBUM: Final = "album"
BPM: Final = "bpm"
# noinspection SpellCheckingInspection
CATALOG_NUMBER: Final = "catalognumber"
COPYRIGHT: Final = "copyright"
DATE: Final = "date"
GENRE: Final = "genre"
PARSED: Final = "parsed"
PUBLISHER: Final = "publisher"
TITLE: Final = "title"
TRACK_NUMBER: Final = "tracknumber"

MP3Tags = {
    ALBUM_ARTIST: "albumartist",
    ALBUM: "album",
    ARTIST: "artist",
    BPM: "bpm",
    CATALOG_NUMBER: "catalognumber",
    COPYRIGHT: "copyright",
    DATE: "date",
    GENRE: "genre",
    PARSED: "parsed",
    PUBLISHER: "publisher",
    TITLE: "title",
    TRACK_NUMBER: "tracknumber",
}
reversed_MP3Tags = {v: k for k, v in MP3Tags.items()}
FLACTags = {
    ALBUM_ARTIST: "ALBUMARTIST",
    ALBUM: "ALBUM",
    ARTIST: "ARTIST",
    BPM: "BPM",
    CATALOG_NUMBER: "CATALOGNUMBER",
    COPYRIGHT: "COPYRIGHT",
    DATE: "DATE",
    GENRE: "GENRE",
    PARSED: "PARSED",
    PUBLISHER: "PUBLISHER",
    TITLE: "TITLE",
}
reversed_FLACTags = {v: k for k, v in FLACTags.items()}

MP4Tags = {
    ALBUM_ARTIST: 'TALB',
    TITLE: '\xa9nam',
    ARTIST: '\xa9ART',
    CATALOG_NUMBER: 'CATA',
    COPYRIGHT: 'cprt',
    DATE: '\xa9day',
    GENRE: '\xa9gen',
    PUBLISHER: 'PUBL',
}
reversed_MP4Tags = {v: k for k, v in MP4Tags.items()}

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
reversed_WAVTags = {v: k for k, v in WAVTags.items()}


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
