"""Which recordings are the same song, and which of them plays.

Separate from scrobble_matching.py on purpose. That module answers "is this listen
about this track", and its base_title() strips `remix` and `bootleg` along with
`edit` -- correct there, ruinous here, because it would merge a remix into the
original and remove it from the library.

Pure functions, no database. The worker owns the SQL.

Design: docs/superpowers/specs/2026-08-23-song-versions-and-canonical-design.md
"""

from __future__ import annotations

import re

from services.music_manager.scrobble_matching import normalize

# Words that describe a length or a packaging of the same recording. A bracketed
# group made only of these is a version marker; one containing anything else
# contains a name, and a name means a different recording.
#
# remix, bootleg, vip, rework, mashup and flip are deliberately absent: those are
# songs of their own and must never group.
_MODIFIER_TOKENS = frozenset(
    {
        'radio',
        'extended',
        'original',
        'album',
        'club',
        'short',
        'full',
        'long',
        'edit',
        'mix',
        'version',
        'cut',
        'official',
        'video',
        'videoclip',
        'clip',
        'visualizer',
        'visualiser',
        'lyric',
        'lyrics',
        'free',
        'download',
        'hq',
        'hd',
        'out',
        'now',
        'preview',
        'remaster',
        'remastered',
        'master',
        'instrumental',
        'acapella',
        'accapella',
        'dub',
    }
)

_TRAILING_BRACKET = re.compile(r'\s*[\(\[]([^\(\)\[\]]*)[\)\]]\s*$')
_TOKEN_SPLIT = re.compile(r'[^\w]+', re.UNICODE)

# Version kinds, best first -- the second tier of the ranking (docs/designs/song-versions/).
# A pro edit or pro mix is the cut made for listening and wins; then the radio edit, a
# plain edit, the original mix, no marker at all (an unmarked single is usually the radio
# cut, an unmarked album track the album version), the extended mix, the instrumental
# family (never what you are looking for), and last anything recorded for a screen: a
# music video, visualizer or "official audio" upload, whose audio is often cut to the
# picture.
KIND_ORDER = ('pro', 'radio', 'edit', 'original', 'none', 'extended', 'instrumental', 'video')

# Checked in this order, so "Radio Instrumental" is instrumental (never canonical), "Radio
# Edit (Official Video)" is a video, "Pro Edit" is pro rather than edit and "Radio Edit"
# radio rather than edit.
_KIND_MARKERS = (
    ('instrumental', ('instrumental', 'acapella', 'accapella', 'dub')),
    ('video', ('video', 'videoclip', 'clip', 'visualizer', 'visualiser', 'audio')),
    ('pro', ('pro',)),
    ('radio', ('radio',)),
    ('extended', ('extended',)),
    ('original', ('original',)),
    ('edit', ('edit',)),
)

# Words that name a kind but are not (yet) part of the grouping vocabulary above. The kind
# detector reads a bracket made of modifiers *or* these; the grouping key does not, so
# adding a kind never regroups the library -- "(Pro Edit)" still keeps its own work until
# the grouping itself learns the word. That is a separate, deliberate change.
_KIND_ONLY_TOKENS = frozenset({'pro', 'music', 'audio'})
_KIND_VOCABULARY = _MODIFIER_TOKENS | _KIND_ONLY_TOKENS

WORK_KEY_MAX = 191

# Reserved key namespaces. Both mean "this work holds exactly one track, and not
# because the song has one version": `split:` is written by the split endpoint in
# routers/songs.py, `track:` by work_key() below. Neither can collide with a real
# key, which always carries the ':::' separator.
UNGROUPABLE_PREFIX = 'track:'
SPLIT_PREFIX = 'split:'

# Past this, a recording is a set or a radio episode rather than a song, and two of
# them sharing a title are two broadcasts rather than two versions. Measured on
# production: 16 hour-long episodes of "Andromedha Guest Mix" sat in one work, 14 of
# "The Boom Room", 11 of "Forerunners Guest Mix" -- 214 works holding 560 long
# recordings, of which 346 would disappear the moment a canonical filter shipped.
#
# The exact number barely matters, which is the useful part: of the tracks in
# multi-version works only 576 run past 10 minutes and 566 past 20, so everything
# long in this library is *very* long and any threshold in that range separates the
# same two populations. 15 minutes is the middle of that empty band.
LONG_FORM_SECONDS = 900


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT.split(text.lower()) if token]


def _strip_version_brackets(title: str, vocabulary: frozenset[str] = _MODIFIER_TOKENS) -> tuple[str, list[str]]:
    """The title without its version markers, plus the tokens that were removed.

    A trailing bracket goes when every token in it comes from `vocabulary`: the grouping
    vocabulary by default, the wider kind vocabulary for `version_kind`.
    """
    stripped: list[str] = []
    result = title
    while True:
        match = _TRAILING_BRACKET.search(result)
        if not match:
            break
        tokens = _tokens(match.group(1))
        if not tokens or not all(token in vocabulary for token in tokens):
            break
        stripped.extend(tokens)
        result = result[: match.start()].strip()
    return result, stripped


def version_free_title(title: str | None) -> str:
    """The normalized title with every version marker removed.

    A bracketed group goes only when all of its tokens are known modifiers, so
    "(Radio Edit)" goes and "(Wildstylez Edit)" stays even though both say "edit".
    """
    if not title:
        return ''
    result, _ = _strip_version_brackets(title)
    return normalize(result)


def version_kind(title: str | None) -> str:
    """Which cut of the recording this is: one of KIND_ORDER.

    Reads the trailing brackets with the kind vocabulary, which is wider than the grouping
    one, so "(Pro Mix)" and "(Official Music Video)" get a kind without changing which
    work the track lands in.
    """
    if not title:
        return 'none'
    _, stripped = _strip_version_brackets(title, _KIND_VOCABULARY)
    for kind, markers in _KIND_MARKERS:
        if any(marker in stripped for marker in markers):
            return kind
    return 'none'


def work_key(artist: str | None, title: str | None, track_id: int, duration_secs: float | None) -> str:
    """The grouping key: one song by one artist, however its versions are spelled.

    A title that normalizes away to nothing identifies no song, so the track gets a
    key of its own rather than sharing the empty one with every other such track.
    Production grouped 117 unrelated recordings that way -- blank titles, a lone
    dove emoji, strings of combining marks -- all under the key ':::'.

    An empty *artist* is not the same case and still groups by title alone. Tracks
    without a primary_artist_id are common in this library and carry the artist in
    the title, where "The Elite - Royals (Radio Edit)" and "The Elite - Royals
    (Extended)" are two versions of one song and have to meet.

    A recording longer than LONG_FORM_SECONDS also gets a key of its own. Two
    hour-long files called "Andromedha Guest Mix" are two episodes of a show, not two
    versions of a song, and grouping them would hide every episode but one behind a
    canonical filter. A long track therefore never groups -- not with another episode
    and not with a short version of the same name, which costs an extended mix its
    place beside its radio edit. That is the safe direction: the failure is showing a
    file twice, not hiding it.

    The track id and the duration are required rather than optional: every caller has
    both, and a default would leave the old behaviour reachable from a caller that
    forgot.
    """
    versionless = version_free_title(title)
    if not versionless:
        return f'{UNGROUPABLE_PREFIX}{track_id}'
    if duration_secs and duration_secs > LONG_FORM_SECONDS:
        return f'{UNGROUPABLE_PREFIX}{track_id}'
    return f'{normalize(artist)}:::{versionless}'[:WORK_KEY_MAX]


# The ranking, decided by Teun on 2026-09-26 (docs/designs/song-versions/): format first,
# driven by the `prefer_lossless` setting, then the version kind, then the bitrate, then
# whether the file is an official release, then -- in SQL -- the oldest.
#
# Bump RANKING_VERSION whenever the order below changes. Every work stores the signature it
# was scored under, and the worker rescores every work whose signature differs (see
# song_version_worker.rescore_once), so a new order reaches the stored scores and the
# canonicals without anyone running anything by hand.
RANKING_VERSION = 2

# Each tier weighted above the maximum of every tier below it, so adding them is still a
# lexicographic comparison. Summing overlapping weights is the defect the first version of
# this model removed; the packing keeps it removed. The largest score, 4*10^8 + 7*10^6 +
# 9990 + 1, fits the INT column with room to spare.
_FORMAT_WEIGHT = 100_000_000
_KIND_WEIGHT = 1_000_000
_BITRATE_WEIGHT = 10
_OFFICIAL_POINTS = 1

# Bitrate is compared in steps, not per kilobit. The derived bitrate carries container and
# tag overhead (a 320 MP3 reads anywhere from 321 to 330), so a per-kilobit comparison
# would let a large embedded cover outvote the official-release tier below it. 32 kbps is
# the smallest step between two real encoder settings.
BITRATE_STEP_KBPS = 32
_BITRATE_STEPS_MAX = 999

_LOSSLESS = frozenset({'flac', 'wav', 'aiff', 'alac'})
_AAC_FAMILY = frozenset({'m4a', 'aac', 'opus', 'ogg'})
_FORMAT_TIERS = 5


def ranking_signature(prefer_lossless: bool) -> str:
    """What a stored score was computed under: the ranking version plus the format setting.

    Flipping the setting changes the signature exactly like a new ranking version does, so
    it triggers the same rescore.
    """
    return f'v{RANKING_VERSION}-{"lossless" if prefer_lossless else "lossy"}'


def derived_bitrate(file_size: int | None, duration_secs: float | None) -> int:
    """Kilobits per second, from the two columns muma actually stores.

    Accurate enough to separate 320 from 192, which is all the format tier asks.
    Container overhead makes it read slightly high; that bias is the same for
    every file, so it never changes an ordering.
    """
    if not file_size or not duration_secs:
        return 0
    return int((file_size * 8) / duration_secs / 1000)


def file_extension(file_path: str | None) -> str:
    """The lowercased extension, '' when there is none."""
    if not file_path or '.' not in file_path:
        return ''
    return file_path.rsplit('.', 1)[-1].lower()


def format_tier(file_path: str, bitrate_kbps: int, prefer_lossless: bool = True) -> int:
    """0 is best.

    With `prefer_lossless` (the default): lossless, MP3 320, AAC and friends, MP3 192, the
    rest. Without it -- storage over fidelity -- MP3 320 first, then AAC, then lossless,
    then the lower bitrates, which is still better than a 128k rip.
    """
    extension = file_extension(file_path)
    lossless = extension in _LOSSLESS
    if prefer_lossless and lossless:
        return 0
    if not lossless and bitrate_kbps >= 300:
        return 0 if not prefer_lossless else 1
    if extension in _AAC_FAMILY:
        return 1 if not prefer_lossless else 2
    if lossless:
        return 2
    if bitrate_kbps >= 180:
        return 3
    return 4


def is_official_release(
    file_path: str | None,
    has_label: bool,
    from_download_archive: bool,
    label_tree_roots: tuple[str, ...] = (),
) -> bool:
    """Whether a file is an official release rather than a rip.

    A file under the label tree counts whatever its tags say -- including one still waiting
    in the import queue (`EPs/__TODO`), which has no label yet but is a proper release all
    the same. Outside the tree a label link counts only when the bytes did not come from a
    download archive: the tagger attaches labels to SoundCloud rips too.
    """
    if file_path:
        for root in label_tree_roots:
            base = root.rstrip('/')
            if base and file_path.startswith(base + '/'):
                return True
    return bool(has_label) and not from_download_archive


def version_score(
    kind: str,
    file_path: str,
    bitrate_kbps: int,
    *,
    is_official: bool,
    prefer_lossless: bool = True,
) -> int:
    """The tiers packed into one sortable integer. Higher is better."""
    format_points = (_FORMAT_TIERS - 1 - format_tier(file_path, bitrate_kbps, prefer_lossless)) * _FORMAT_WEIGHT

    try:
        kind_index = KIND_ORDER.index(kind)
    except ValueError:
        kind_index = KIND_ORDER.index('none')
    kind_points = (len(KIND_ORDER) - 1 - kind_index) * _KIND_WEIGHT

    steps = min(max(bitrate_kbps, 0) // BITRATE_STEP_KBPS, _BITRATE_STEPS_MAX)
    bitrate_points = steps * _BITRATE_WEIGHT

    official_points = _OFFICIAL_POINTS if is_official else 0

    return format_points + kind_points + bitrate_points + official_points
