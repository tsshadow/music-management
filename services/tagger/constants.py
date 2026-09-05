from enum import Enum
from typing import Final

ARTIST_REGEX: Final = '(?i)\\s(&|，|aka|and|b2b|b3b|feat\\.?|featuring|features|ft|ft\\.?|invite|invites|meets|pres\\.?|present|presents|presenting|versus|vs\\.?|with|x|\\+|,|et)\\s|,\\s|，\\s|presents:\\s|present:\\s|:\\s'
ARTIST_REGEX_NON_CAPTURING: Final = '(?i)\\s(?:&|:\\s|，|aka|and|b2b|b3b|feat\\.?|featuring|features|ft\\.?|invite|invites|meets|pres\\.?|present|presents|presenting|versus|vs\\.?|with|x|\\+|,|et)\\s|,\\s|，\\s|presents:\\s|present:\\s|:\\s'
ALBUM_ARTIST: Final = 'albumartist'
ARTIST: Final = 'artist'
REMIXER: Final = 'remixer'
ALBUM: Final = 'album'
BPM: Final = 'bpm'
CATALOG_NUMBER: Final = 'catalognumber'
COPYRIGHT: Final = 'copyright'
DATE: Final = 'date'
FESTIVAL: Final = 'festival'
GENRE: Final = 'genre'
# The radio show or podcast series a long mix belongs to, and its episode number within
# that series. Kept apart from ALBUM/TRACK_NUMBER on purpose: those already hold values
# the tagger computes for a download's channel, and overwriting them is not reversible.
PODCAST: Final = 'podcast'
PODCAST_EPISODE: Final = 'podcast_episode'
PARSED: Final = 'parsed'
PUBLISHER: Final = 'publisher'
TITLE: Final = 'title'
ORIGINAL_TITLE: Final = 'original_title'
# The artist tag as read off the file, before CleanTagsRule's regex splits "feat"/"vs"/"&" into
# separate values and discards the joiner word. Only ever set when that split actually changes
# something -- see CleanTagsRule -- so a plain single-artist file never grows this tag at all.
ORIGINAL_ARTIST: Final = 'original_artist'
# The original release date, as opposed to DATE which is this edition's. LMS prefers the original
# everywhere it sorts and for the Memories anniversary match, so this is where a resolved release
# date belongs. The value doubles as the EasyID3 key, which writes a real TDOR frame.
ORIGINAL_DATE: Final = 'originaldate'
RATING: Final = 'rating'
TRACK_NUMBER: Final = 'tracknumber'
MP3Tags = {
    ALBUM_ARTIST: 'albumartist',
    ALBUM: 'album',
    ARTIST: 'artist',
    BPM: 'bpm',
    CATALOG_NUMBER: 'catalognumber',
    COPYRIGHT: 'copyright',
    DATE: 'date',
    ORIGINAL_DATE: 'originaldate',
    FESTIVAL: 'festival',
    PODCAST: 'podcast',
    PODCAST_EPISODE: 'podcast_episode',
    GENRE: 'genre',
    PARSED: 'parsed',
    PUBLISHER: 'publisher',
    REMIXER: 'remixer',
    TITLE: 'title',
    ORIGINAL_TITLE: 'original_title',
    ORIGINAL_ARTIST: 'original_artist',
    RATING: 'rating',
    TRACK_NUMBER: 'tracknumber',
}
reversed_MP3Tags = {v: k for k, v in MP3Tags.items()}
FLACTags = {
    ALBUM_ARTIST: 'ALBUMARTIST',
    ALBUM: 'ALBUM',
    ARTIST: 'ARTIST',
    BPM: 'BPM',
    CATALOG_NUMBER: 'CATALOGNUMBER',
    COPYRIGHT: 'COPYRIGHT',
    DATE: 'DATE',
    ORIGINAL_DATE: 'ORIGINALDATE',
    FESTIVAL: 'FESTIVAL',
    PODCAST: 'PODCAST',
    PODCAST_EPISODE: 'PODCAST_EPISODE',
    GENRE: 'GENRE',
    PARSED: 'PARSED',
    PUBLISHER: 'PUBLISHER',
    REMIXER: 'REMIXER',
    TITLE: 'TITLE',
    ORIGINAL_TITLE: 'ORIGINAL_TITLE',
    ORIGINAL_ARTIST: 'ORIGINAL_ARTIST',
    RATING: 'RATING',
}
reversed_FLACTags = {v: k for k, v in FLACTags.items()}
OPUSTags = {
    ALBUM_ARTIST: 'ALBUMARTIST',
    ALBUM: 'ALBUM',
    ARTIST: 'ARTIST',
    BPM: 'BPM',
    CATALOG_NUMBER: 'CATALOGNUMBER',
    COPYRIGHT: 'COPYRIGHT',
    DATE: 'DATE',
    ORIGINAL_DATE: 'ORIGINALDATE',
    FESTIVAL: 'FESTIVAL',
    PODCAST: 'PODCAST',
    PODCAST_EPISODE: 'PODCAST_EPISODE',
    GENRE: 'GENRE',
    PARSED: 'PARSED',
    PUBLISHER: 'PUBLISHER',
    REMIXER: 'REMIXER',
    TITLE: 'TITLE',
    ORIGINAL_TITLE: 'ORIGINAL_TITLE',
    ORIGINAL_ARTIST: 'ORIGINAL_ARTIST',
    RATING: 'RATING',
}
reversed_OPUSTags = {v: k for k, v in OPUSTags.items()}
AACTags = {
    ALBUM_ARTIST: 'ALBUMARTIST',
    ALBUM: 'ALBUM',
    ARTIST: 'ARTIST',
    BPM: 'BPM',
    CATALOG_NUMBER: 'CATALOGNUMBER',
    COPYRIGHT: 'COPYRIGHT',
    DATE: 'DATE',
    ORIGINAL_DATE: 'ORIGINALDATE',
    FESTIVAL: 'FESTIVAL',
    PODCAST: 'PODCAST',
    PODCAST_EPISODE: 'PODCAST_EPISODE',
    GENRE: 'GENRE',
    PARSED: 'PARSED',
    PUBLISHER: 'PUBLISHER',
    TITLE: 'Title',
}
reversed_AACTags = {v: k for k, v in AACTags.items()}
MP4Tags = {
    ALBUM_ARTIST: 'TALB',
    TITLE: '©nam',
    ARTIST: '©ART',
    CATALOG_NUMBER: 'CATA',
    COPYRIGHT: 'cprt',
    DATE: '©day',
    GENRE: '©gen',
    PUBLISHER: 'PUBL',
    REMIXER: 'REMIXER',
    ORIGINAL_TITLE: 'ORIGINAL_TITLE',
    # ORIGINAL_ARTIST is deliberately unmapped here: an M4A atom name outside the
    # `----:` freeform namespace gets truncated to 4 bytes by mutagen, so mapping
    # it to a bare 'ORIGINAL_ARTIST' the way ORIGINAL_TITLE is mapped above would
    # collide onto the same 'ORIG' atom as ORIGINAL_TITLE. Leaving it unmapped
    # routes it through _set_m4a_tag's freeform-atom fallback instead
    # (`----:com.apple.iTunes:ORIGINAL_ARTIST`), which doesn't have that limit.
}
reversed_MP4Tags = {v: k for k, v in MP4Tags.items()}
WAVTags = {
    ALBUM: 'TALB',
    ALBUM_ARTIST: 'TPE2',
    ARTIST: 'TPE1',
    CATALOG_NUMBER: 'TXXX:CATALOGNUMBER',
    COPYRIGHT: 'TCOP',
    DATE: 'TDRC',
    ORIGINAL_DATE: 'TDOR',
    GENRE: 'TCON',
    PUBLISHER: 'TPUB',
    TITLE: 'TIT2',
    FESTIVAL: 'TXXX:FESTIVAL',
    PODCAST: 'TXXX:PODCAST',
    PODCAST_EPISODE: 'TXXX:PODCAST_EPISODE',
    REMIXER: 'TXXX:REMIXER',
    ORIGINAL_TITLE: 'TXXX:ORIGINAL_TITLE',
    ORIGINAL_ARTIST: 'TXXX:ORIGINAL_ARTIST',
    RATING: 'TXXX:RATING',
}
reversed_WAVTags = {v: k for k, v in WAVTags.items()}


class FormatEnum(Enum):
    NONE = 0
    RECAPITALIZE = 1


class SongTypeEnum(Enum):
    NONE = 0
    LABEL = 1
    YOUTUBE = 2
    SOUNDCLOUD = 3
    GENERIC = 4
    TELEGRAM = 5


class MusicFileType(Enum):
    NONE = 0
    MP3 = 1
    FLAC = 2
    WAV = 3
    M4A = 4
    AAC = 5
    OPUS = 6
