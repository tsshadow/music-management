"""What a file *is* -- a track, a set, a live set, a podcast episode or talk -- and when a live set was played.

Talk is an interview or the preview of an event DVD: the two non-music forms
(docs/designs/non-music-forms/).

`SongTypeEnum` records where a file came from (SoundCloud, a label, ...), never what it is, and until
this module nothing did: the songs/sets switch splits on ten minutes and that was all. See
docs/designs/track-form/ and docs/product-goal.md, "What \"from 2012\" means".

**One derivation, from facts the database already holds.** The inputs are the path, the title and
the duration -- exactly what `library_tracks` and `library_media_files` store -- so the scanner (one
file) and the hourly pass (the whole library, `services/music_manager/track_form_sync.py`) compute
from the same facts and cannot disagree with each other. The festival and podcast lookups are the
helpers the tagger's `InferFestivalFromTitleRule` and `InferPodcastFromTitleRule` use, called the
same way; those rules write the FESTIVAL and PODCAST tags from these very inputs, so reading the tags
back would answer the same question at the price of a file read per track.
"""

from __future__ import annotations

import re

TRACK = 'track'
SET = 'set'
LIVESET = 'liveset'
PODCAST = 'podcast'
INTERVIEW = 'interview'
PREVIEW = 'preview'

#: Every form, in the order a picker lists them. A closed set: the LMS endpoints refuse anything
#: else, and so does the MuMa filter.
FORMS = (TRACK, SET, LIVESET, PODCAST, INTERVIEW, PREVIEW)

#: The forms that are not music: talk and DVD trailers among the downloads. They stay in the
#: library and in search, and every music feature leaves them out -- the LMS lists, shuffles and
#: radio (`FindParameters::excludeNonMusic`), the feeds, the song versions, the library count.
#: docs/designs/non-music-forms/.
NON_MUSIC_FORMS = frozenset({INTERVIEW, PREVIEW})

#: Below this a file is a track, wherever it sits. The threshold the tagger's festival and podcast
#: rules and the LMS LENGTH cluster already use. Decided first because the short files under
#: `Podcasts/` and `Top 100/` are the individual tracks of a countdown, not episodes.
MIN_SET_SECONDS = 600

#: Top-level folders whose long files are one form by construction. Keys are lower case.
#: `Telegram` because that channel is where the festival rips arrive (product-goal.md, "How music
#: arrives"); `Warm Up Mixes` needs no entry, it is the default `set`.
FOLDER_FORMS = {
    'livesets': LIVESET,
    'telegram': LIVESET,
    'podcasts': PODCAST,
}

#: Top-level folders that hold label releases (`EPs/<label>/<release>/`). Their titles name
#: festivals all the time -- "Decibel Dictature" is a track, "Defqon.1 2015 Mix 1" is the label's
#: mix album for that edition -- so there a festival match alone only makes a `set` (bug report 109).
LABEL_FOLDERS = frozenset({'eps'})

#: What marks a label release as a recording of the event itself: "Live at Reverze 2009", "The
#: Live Registration", a DVD rip. Matched as whole words after `_ - . ( ) [ ]` became spaces, so
#: "Qlimax_2005-DVD-2006" and "Tha_Playah_Live-STREAM" count and "Oliver" or "delivery" do not.
_LIVE_MARKER = re.compile(r'\b(live|livesets?|dvda?)\b')
_SEPARATORS = re.compile(r'[_\-.()\[\]]+')

#: Top-level folders the downloaders fill. Only there does "interview" in a title mean talk: a
#: label release can be a song called "Interview".
DOWNLOAD_FOLDERS = frozenset({'youtube', 'soundcloud'})

#: "Interview" or "Interviews" as a whole word: "Ground Zero Festival 2014 - Lenny Dee Interview".
_INTERVIEW = re.compile(r'(?<![a-z])interviews?(?![a-z])', re.IGNORECASE)

#: A word that says the upload is music with some talk in it -- "Pat B At Topradio Liveset +
#: Interview", "Going To An Interview (Outro Storytelling Audio)" -- so the interview rule skips it.
_MUSIC_WORD = re.compile(r'(?<![a-z])(sets?|live ?sets?|mix|intro|outro)(?![a-z])', re.IGNORECASE)

#: The trailer of an event DVD: "DVD Preview", "Blu-ray;DVD Preview", "Preview DVD". A plain
#: "(Preview)" is a producer's snippet of a real song and stays music.
_DVD_PREVIEW = re.compile(
    r'(?<![a-z])(dvd|blu-?ray)(?![a-z]).{0,10}(?<![a-z])preview(?![a-z])'
    r'|(?<![a-z])preview(?![a-z]).{0,10}(?<![a-z])(dvd|blu-?ray)(?![a-z])',
    re.IGNORECASE,
)


def _top_folder(path: str | None, music_root: str | None) -> str:
    """The first folder below the music root, lower-cased, or '' when the path is not under it."""
    if not path:
        return ''
    parts = [part for part in path.split('/') if part]
    root_parts = [part for part in str(music_root or '').split('/') if part]
    if root_parts:
        if parts[: len(root_parts)] != root_parts:
            return ''
        parts = parts[len(root_parts) :]
    # A file loose in the root has no folder.
    if len(parts) < 2:
        return ''
    return parts[0].lower()


def _names_a_live_recording(path: str | None, title: str | None) -> bool:
    """Whether the title or the path says the file was recorded at the event (live, DVD)."""
    haystack = _SEPARATORS.sub(' ', f'{title or ""} {path or ""}'.lower())
    return bool(_LIVE_MARKER.search(haystack))


def _festival_matches(path: str | None, title: str | None, festivals) -> list[dict]:
    """Festival matches the way `InferFestivalFromTitleRule` finds them: title first, else path with a year."""
    if festivals is None:
        return []
    matches = festivals.get_all(title) if title else []
    if not matches and path:
        # A bare folder name is too weak: an artist folder called Rebelion is not the festival
        # Rebellion. Same guard as the tagger rule.
        matches = festivals.get_all(path, require_year=True)
    return matches


def derive_non_music_form(path: str | None, music_root: str | None, title: str | None) -> str | None:
    """`interview` or `preview` when the title marks the file as talk, otherwise None.

    The title decides, not the length: a 12-minute interview is an interview, and a DVD preview is
    a preview at any length (docs/designs/non-music-forms/).
    """
    if not title:
        return None
    if _DVD_PREVIEW.search(title):
        return PREVIEW
    if _INTERVIEW.search(title) and not _MUSIC_WORD.search(title) and _top_folder(path, music_root) in DOWNLOAD_FOLDERS:
        return INTERVIEW
    return None


def derive_form(
    path: str | None,
    music_root: str | None,
    duration_secs: float | None,
    title: str | None,
    festivals=None,
    podcasts=None,
) -> str | None:
    """The form of one file, or None when its length is unknown.

    First hit wins: a non-music title, then length, then the folder, then an approved podcast show,
    then a festival. Podcast before festival because "Defqon.1 Podcast #12" names a festival and is
    an episode. In the label tree a festival counts only together with a live marker (bug report 109).
    A non-music title needs no duration, every other form does.
    """
    non_music = derive_non_music_form(path, music_root, title)
    if non_music:
        return non_music
    if not duration_secs or duration_secs <= 0:
        return None
    if duration_secs < MIN_SET_SECONDS:
        return TRACK

    top_folder = _top_folder(path, music_root)
    folder_form = FOLDER_FORMS.get(top_folder)
    if folder_form:
        return folder_form

    if podcasts is not None:
        haystack = f'{title or ""} {path or ""}'.strip()
        if haystack and podcasts.get(haystack):
            return PODCAST

    if _festival_matches(path, title, festivals):
        if top_folder in LABEL_FOLDERS and not _names_a_live_recording(path, title):
            return SET
        return LIVESET
    return SET


def derive_performance_date(form: str | None, path: str | None, title: str | None, festivals=None) -> str | None:
    """The day a live set was played, `YYYY-MM-DD`, or None.

    Only a live set has one, and only when a festival match carries a year for which the festival
    has an edition date (`rules_festival_editions`). The first match that knows a date wins -- the
    same choice the tagger makes when it writes that date into the file's DATE tag.
    """
    if form != LIVESET:
        return None
    for match in _festival_matches(path, title, festivals):
        if match.get('date'):
            return str(match['date'])[:10]
    return None


def classify(path, music_root, duration_secs, title, festivals=None, podcasts=None) -> tuple[str | None, str | None]:
    """`(form, performance_date)` for one file -- the pair both writers store."""
    form = derive_form(path, music_root, duration_secs, title, festivals, podcasts)
    return form, derive_performance_date(form, path, title, festivals)
