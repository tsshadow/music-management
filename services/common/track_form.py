"""What a file *is* -- a track, a set, a live set or a podcast episode -- and when a live set was played.

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

TRACK = 'track'
SET = 'set'
LIVESET = 'liveset'
PODCAST = 'podcast'

#: Every form, in the order a picker lists them. A closed set: the LMS endpoints refuse anything
#: else, and so does the MuMa filter.
FORMS = (TRACK, SET, LIVESET, PODCAST)

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


def derive_form(
    path: str | None,
    music_root: str | None,
    duration_secs: float | None,
    title: str | None,
    festivals=None,
    podcasts=None,
) -> str | None:
    """The form of one file, or None when its length is unknown.

    First hit wins: length, then the folder, then an approved podcast show, then a festival.
    Podcast before festival because "Defqon.1 Podcast #12" names a festival and is an episode.
    """
    if not duration_secs or duration_secs <= 0:
        return None
    if duration_secs < MIN_SET_SECONDS:
        return TRACK

    folder_form = FOLDER_FORMS.get(_top_folder(path, music_root))
    if folder_form:
        return folder_form

    if podcasts is not None:
        haystack = f'{title or ""} {path or ""}'.strip()
        if haystack and podcasts.get(haystack):
            return PODCAST

    if _festival_matches(path, title, festivals):
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
