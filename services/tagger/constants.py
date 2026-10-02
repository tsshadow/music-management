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
# Which rung of the release-date ladder ORIGINAL_DATE came from: deezer, nfo-street, nfo-release,
# tag, nfo-rip or arrival (InferReleaseDateFromNfoRule, docs/designs/release-info-enrichment/).
# A better rung may replace a worse one later; without this tag a full date is never replaced.
DATE_SOURCE: Final = 'date_source'
# The release's UPC/EAN as a store reports it. Never a catalogue number; kept for lookups.
BARCODE: Final = 'barcode'
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
    DATE_SOURCE: 'date_source',
    BARCODE: 'barcode',
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
    DATE_SOURCE: 'DATE_SOURCE',
    BARCODE: 'BARCODE',
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
    DATE_SOURCE: 'DATE_SOURCE',
    BARCODE: 'BARCODE',
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
    DATE_SOURCE: 'DATE_SOURCE',
    BARCODE: 'BARCODE',
    FESTIVAL: 'FESTIVAL',
    PODCAST: 'PODCAST',
    PODCAST_EPISODE: 'PODCAST_EPISODE',
    GENRE: 'GENRE',
    PARSED: 'PARSED',
    PUBLISHER: 'PUBLISHER',
    TITLE: 'Title',
}
reversed_AACTags = {v: k for k, v in AACTags.items()}
# The namespace for the m4a atoms this tagger invents. mutagen writes every atom name outside
# it as exactly 4 bytes and silently truncates a longer one: a bare 'REMIXER' landed on disk as
# 'REMI' and 'ORIGINAL_TITLE' as 'ORIG', and neither was ever read back. So every m4a with a
# remixer was rewritten on every retag, and InferArtistFromTitleRule re-seeded ORIGINAL_TITLE
# from the already-cleaned title and inferred again from the remainder. Every custom name longer
# than 4 bytes therefore lives under this prefix: REMIXER and ORIGINAL_TITLE explicitly below,
# and every unmapped name (ORIGINAL_ARTIST, FESTIVAL, PODCAST, PARSED, ...) through
# BaseSong._set_m4a_tag's freeform fallback. The 4-byte 'CATA' and 'PUBL' are not affected.
# A freeform atom holds bytes (MP4FreeForm): TagCollection._parse_m4a decodes them and
# BaseSong._set_m4a_tag encodes them, so a value reads back exactly as it was written.
MP4_FREEFORM_PREFIX: Final = '----:com.apple.iTunes:'
MP4Tags = {
    ALBUM: '©alb',
    ALBUM_ARTIST: 'aART',
    TITLE: '©nam',
    ARTIST: '©ART',
    CATALOG_NUMBER: 'CATA',
    COPYRIGHT: 'cprt',
    DATE: '©day',
    GENRE: '©gen',
    PUBLISHER: 'PUBL',
    REMIXER: MP4_FREEFORM_PREFIX + 'REMIXER',
    ORIGINAL_TITLE: MP4_FREEFORM_PREFIX + 'ORIGINAL_TITLE',
}
reversed_MP4Tags = {v: k for k, v in MP4Tags.items()}
# Where earlier versions put a tag on m4a, keyed by that atom. 'REMI' and 'ORIG' are the
# truncated names described above; 'TALB' is the ID3 album frame name, which was mapped as the
# album artist's atom; the album itself had no mapping and fell through to a freeform ALBUM
# atom that LMS does not read. TagCollection reads a legacy atom when the correct one is
# absent, and BaseSong deletes it on the next save, so a file heals on its next retag.
LEGACY_MP4_ATOMS = {
    'REMI': REMIXER,
    'ORIG': ORIGINAL_TITLE,
    'TALB': ALBUM_ARTIST,
    MP4_FREEFORM_PREFIX + 'ALBUM': ALBUM,
}
WAVTags = {
    ALBUM: 'TALB',
    ALBUM_ARTIST: 'TPE2',
    ARTIST: 'TPE1',
    CATALOG_NUMBER: 'TXXX:CATALOGNUMBER',
    COPYRIGHT: 'TCOP',
    DATE: 'TDRC',
    ORIGINAL_DATE: 'TDOR',
    DATE_SOURCE: 'TXXX:DATE_SOURCE',
    BARCODE: 'TXXX:BARCODE',
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
    """How the tagger formats a value it writes back."""

    NONE = 0
    RECAPITALIZE = 1


class SongTypeEnum(Enum):
    """Where a song came from, which decides the rules it is tagged with."""

    NONE = 0
    LABEL = 1
    YOUTUBE = 2
    SOUNDCLOUD = 3
    GENERIC = 4
    TELEGRAM = 5


class MusicFileType(Enum):
    """The audio container of a file, which decides how its tags are read and written."""

    NONE = 0
    MP3 = 1
    FLAC = 2
    WAV = 3
    M4A = 4
    AAC = 5
    OPUS = 6
