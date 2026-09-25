import os
import re
import threading
from difflib import SequenceMatcher, get_close_matches

from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.common.Helpers.TableHelper import TableHelper
from services.common.Helpers.TrustedArtistHelper import TrustedArtistHelper
from services.tagger.constants import ARTIST, ARTIST_REGEX_NON_CAPTURING, ORIGINAL_TITLE, TITLE
from services.tagger.Song.rules.TagRule import TagRule

# "Thunderdome 2025", "Emporium 2025", "Snakepit 2024": an edition, never an artist.
YEAR_SUFFIX_PATTERN = re.compile(r'\b(19[89]\d|20[0-4]\d)\s*$')
PIPE_CHARACTERS = ('｜', '|')


def artist_index(artist_db) -> dict[str, str]:
    """lower-cased name -> name as stored, for every known artist.

    Built once per file by three different rules, and until 0.66.1 each build was a full
    read of library_artists (57k rows) -- 1.6 s of the 2.2 s a Soundcloud file cost. A
    caching TableHelper hands out its own snapshot; anything else (the test doubles) is
    read the old way.
    """
    if isinstance(artist_db, TableHelper):
        return artist_db.lowercase_map()
    return {name.lower(): name for name in artist_db.get_all_values() if name}


def has_close_artist(word: str, names, cutoff: float) -> bool:
    """Whether any known name is at least `cutoff` similar to `word`.

    The same answer as `bool(get_close_matches(word, names, n=1, cutoff))` -- same matcher,
    same three ratio gates in the same order -- but an exact hit is a set lookup and a
    fuzzy hit returns at the first name that passes instead of scoring all 37k. Only a
    miss still costs the full scan.
    """
    if word in names:
        return True
    matcher = SequenceMatcher(None, '', word)
    for name in names:
        matcher.set_seq1(name)
        if matcher.real_quick_ratio() >= cutoff and matcher.quick_ratio() >= cutoff and matcher.ratio() >= cutoff:
            return True
    return False


def extract_artists_from_string(part: str) -> list[str]:
    return [a.strip() for a in re.split(ARTIST_REGEX_NON_CAPTURING, part) if a.strip()]


def normalise_pipes(title: str) -> str:
    """Both pipe characters, as one separator.

    SoundCloud's promo titles use the fullwidth `｜` because the plain `|` is not allowed in a
    filename, so the two spellings mean the same thing and every rule below has to see the same
    string. Three of them only replaced the ASCII one, which left "PREMIERE ｜ TARS - Rumble" as a
    two-segment title whose first segment is "PREMIERE ｜ TARS" -- an artist name that never
    existed.
    """
    for pipe in PIPE_CHARACTERS:
        title = title.replace(pipe, '-')
    return title


def looks_like_an_event(segment: str, festival_helper=None) -> bool:
    """
    True for a segment that names an event rather than a performer.

    A trailing year is the signal that needs no database: artists do not end
    their name in 2025, editions do. The festival helper catches the rest, but
    only knows the names that have been entered, so it cannot carry this alone.
    """
    if not segment:
        return False
    if YEAR_SUFFIX_PATTERN.search(segment.strip()):
        return True
    if festival_helper:
        try:
            return bool(festival_helper.get(segment))
        except Exception:
            return False
    return False


def names_in(text: str | None) -> list[str]:
    """The artist names a written credit contains, lowercased for comparison."""
    return [name.strip().lower() for name in extract_artists_from_string(text or '') if name.strip()]


def remember_display_artist(song, source: str | None, cleaned: list[str]) -> None:
    """Offer the credit as written as this file's display artist, if it is one.

    CleanTagsRule captures the artist line as written for a file whose own ARTIST tag
    still needed splitting. A download's artists do not arrive that way: they come out
    of the title, and the rules below hand the ARTIST tag over already split, so by the
    time CleanTagsRule sees it there is nothing left to preserve and its
    `original != split` test never fires. Every SoundCloud and YouTube track therefore
    lost its "Lil Texas & Albino" -- 8 of 344757 tracks on production carried a display
    artist.

    Only a credit that *is* the artist list, spelled differently, is offered. The text a
    name was read out of is not automatically a credit worth showing: `set_cleaned_artist`
    below strips bracketed annotations and trailing words like "live", and the fuzzy
    branches of the single-dash rule keep only the candidates that matched a known
    artist. Recording the raw segment in those cases would put "Angerfist (live)" or a
    name the library deliberately rejected on the track as its credit -- and consumers
    prefer the display artist over the artist list, so that credit is what a reader sees.

    So this only remembers, and only when the segment splits to exactly the names that
    came out of it. `CaptureDisplayArtistRule` decides afterwards whether to write it,
    because the rules that follow this one can still add artists the credit does not
    name.
    """
    if not source:
        return
    source = source.strip()
    if not source or source == ';'.join(cleaned):
        return
    if names_in(source) != [name.lower() for name in cleaned]:
        return
    song.display_artist_candidate = source


def set_cleaned_artist(song, library_artists: str | list[str], artist_db=None, source: str | None = None) -> bool:
    """Write the ARTIST tag from names read out of a title.

    `source` is the raw text those names were read from -- the segment as the title
    spelled it, separators and all. It is what becomes the display artist; see
    capture_display_artist.
    """
    if isinstance(library_artists, str):
        library_artists = [library_artists]
    blacklist = {
        'live',
        'dj set',
        'set',
        'remix',
        'edit',
        'extended mix',
        'mix',
        'version',
        'remix edit',
        'remix pro',
        'a1 ',
        'a2 ',
        'b1 ',
        'b2 ',
    }
    artist_db = artist_db or TrustedArtistHelper()
    all_artists = artist_index(artist_db)
    cleaned = []
    for a in library_artists:
        raw = a.strip()
        base = re.sub('\\s*[\\(\\[\\{<][^()\\[\\]{}<>]*[\\)\\]\\}>]', '', raw).strip()
        words = base.split()
        while words and words[-1].lower() in blacklist:
            words.pop()
        base = ' '.join(words).strip()
        if not base:
            continue
        corrected = all_artists.get(base.lower(), base)
        cleaned.append(corrected)
    if not cleaned:
        return False
    song.tag_collection.set_item(ARTIST, ';'.join(cleaned))
    remember_display_artist(song, source, cleaned)
    return True


class InferArtistFromTitleRule(TagRule):
    """Reads the artist out of a download's title with the first of its sub-rules that matches."""

    def __init__(
        self,
        artist_db=None,
        ignored_db: FilterTableHelper = None,
        genre_db: FilterTableHelper = None,
        festival_helper=None,
    ):
        from services.common.Helpers.Cache import databaseHelpers

        self.artist_db = artist_db or databaseHelpers.get('library_artists') or TrustedArtistHelper()
        self.festival_helper = festival_helper or databaseHelpers.get('festivalHelper')
        self.genre_db = genre_db or databaseHelpers.get('rules_genres')
        if self.genre_db:
            all_genres = self.genre_db.get_all()
            all_genres = {genre.lower() for genre in all_genres if genre}
        else:
            all_genres = set()
        all_genres.add('saturday')
        all_genres.add('sunday')
        all_genres.add('friday')
        all_genres.add('mainstage')
        ignored_helper = ignored_db or databaseHelpers.get('rules_ignored_artists')
        ignored_names = ignored_helper.get_all() if ignored_helper else []
        # A name on the ignore list with no correction has been judged not to be an artist at all.
        # Every rule below picks its segment by matching against `artist_names`, so leaving such a
        # name in that set is what lets a promo marker win a title: "PREMIERE ｜ TARS - Rumble"
        # scored "Premiere" 1.05 against itself and "TARS" not at all, took the marker as the
        # artist and left the real one inside the title. That put 9.188 tracks under one
        # non-existent artist on production, and it feeds itself -- the name is in library_artists
        # *because* an earlier pass read it out of a title.
        #
        # A name that carries a correction stays selectable on purpose: picking it is how
        # CheckArtistRule gets the chance to swap in the spelling the correction names.
        self.ignored_without_correction = {
            name.lower() for name in ignored_names if not ignored_helper.get_corrected(name)
        }
        self._ignored_names = ignored_names
        self._all_genres = all_genres
        # The rule outlives a file since the rule stack is built once per round (see
        # services/tagger/Song/rule_stack.py), and library_artists publishes a new snapshot
        # mid-round -- once a minute, and whenever an artist is added. A rule built per file
        # always saw the latest one; `_current_rules` rebuilds the name sets when the
        # snapshot changes, so a round-long rule sees exactly what a per-file one did.
        self._lock = threading.Lock()
        self._artist_snapshot = self._snapshot_of_artists()
        names = self._artist_snapshot if self._artist_snapshot is not None else artist_index(self.artist_db)
        self.rules = self._build_rules(set(names))

    def _snapshot_of_artists(self):
        """The artist helper's current snapshot object, or None when it has no such thing.

        Only a caching TableHelper publishes one: it replaces its map on every change and
        never mutates it, so identity says whether anything changed. A test double has no
        snapshot to follow and keeps the names it was built with, as it always did.
        """
        if isinstance(self.artist_db, TableHelper):
            return self.artist_db.lowercase_map()
        return None

    def _build_rules(self, artist_names: set[str]) -> list[TagRule]:
        """The sub-rules, in the order they are tried, over one set of artist names."""
        # See the comment on ignored_without_correction in __init__.
        artist_names -= self.ignored_without_correction
        return [
            InferArtistFromPresentsOrColonRule(self.artist_db),
            InferArtistFromTitleAtRule(self._ignored_names, self.artist_db),
            InferArtistFromEventPrefixRule(artist_names, self.artist_db, self._all_genres, self.festival_helper),
            InferArtistFromTitleByRule(artist_names, self.artist_db),
            InferArtistFromTitleDotRule(artist_names, self.artist_db),
            InferArtistFromTitleSingleDashRule(artist_names, self.artist_db, self.festival_helper),
            InferArtistFromTitleMultiDashRule(artist_names, self.artist_db, self._all_genres, self.festival_helper),
            InferArtistFromFirstSegmentFallbackRule(
                self.artist_db, self.festival_helper, self.ignored_without_correction
            ),
            InferArtistFromTitleFallbackRule(self._ignored_names),
        ]

    def _current_rules(self) -> list[TagRule]:
        """The sub-rules over the artist snapshot as it is now; rebuilt only when it changed."""
        if self._artist_snapshot is None:
            return self.rules
        snapshot = self._snapshot_of_artists()
        if snapshot is self._artist_snapshot:
            return self.rules
        with self._lock:
            if snapshot is not self._artist_snapshot:
                self.rules = self._build_rules(set(snapshot))
                self._artist_snapshot = snapshot
            return self.rules

    def apply(self, song):
        if not song.tag_collection.has_item(ORIGINAL_TITLE):
            song.tag_collection.set_item(ORIGINAL_TITLE, song.tag_collection.get_item_as_string(TITLE))
        for rule in self._current_rules():
            if rule.apply(song):
                print(f"[InferArtistFromTitle] Applied rule: {rule.__class__.__name__} on '{song.path()}'")
                return


class InferArtistFromEventPrefixRule(TagRule):
    """
    Reads "Thunderdome 2025 | Akimbo vs. Barber" as the event it is: the edition
    on the left, the artists who played it on the right.

    Without this the first segment is taken as the artist, "Thunderdome 2025"
    ends up in library_artists, and from then on the single dash rule matches it
    exactly -- so every later scan confirms the mistake instead of repairing it.
    The right hand side has to look like a performer before we act on it: a lone
    unknown phrase is far more likely to be a stage or a theme than an artist.
    """

    def __init__(self, artist_names, artist_db, blocked_names, festival_helper=None):
        self.artist_names = artist_names
        self.artist_db = artist_db
        self.blocked_names = blocked_names or set()
        self.festival_helper = festival_helper

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        if not title:
            return False
        title = normalise_pipes(title)
        segments = [s.strip() for s in title.split(' - ') if s.strip()]
        if len(segments) != 2:
            return False
        event, performers = segments
        if not looks_like_an_event(event, self.festival_helper):
            return False
        if looks_like_an_event(performers, self.festival_helper):
            return False
        candidates = extract_artists_from_string(performers)
        if not candidates or not self._looks_like_artists(candidates):
            return False
        set_cleaned_artist(song, candidates, self.artist_db, source=performers)
        song.tag_collection.set_item(TITLE, event)
        return True

    def _looks_like_artists(self, candidates):
        if any(c.lower() in self.blocked_names for c in candidates):
            return False
        if any(c.lower() in self.artist_names for c in candidates):
            return True
        if any(has_close_artist(c.lower(), self.artist_names, cutoff=0.75) for c in candidates):
            return True
        # "Akimbo vs. Barber" split in two: the separator itself says these are
        # performers, which is what lets a brand new name through the first time.
        return len(candidates) > 1


class InferArtistFromTitleDotRule(TagRule):
    def __init__(self, rules_ignored_artists, artist_db):
        self.rules_ignored_artists = {a.lower() for a in rules_ignored_artists}
        self.artist_db = artist_db

    def apply(self, song):
        CATALOG_PATTERN = re.compile('^(GB[EDH]\\d{3,})[.\\s]+(.*?)\\s+-\\s+(.*)')
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        if not title and ('. ' not in title) and (' - ' not in title):
            return False
        match = CATALOG_PATTERN.match(title)
        if not match:
            return False
        artist_str = match.group(2).strip()
        rest_of_title = match.group(3).strip()
        if not artist_str:
            return False
        library_artists = extract_artists_from_string(artist_str)
        set_cleaned_artist(song, library_artists, self.artist_db, source=artist_str)
        song.tag_collection.set_item(TITLE, rest_of_title)
        return True


class InferArtistFromTitleAtRule(TagRule):
    def __init__(self, rules_ignored_artists, artist_db):
        self.rules_ignored_artists = {a.lower() for a in rules_ignored_artists}
        self.artist_db = artist_db

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        if not title:
            return False
        if ' @ ' not in title:
            return False
        parts = title.split(' @ ', 1)
        library_artists = extract_artists_from_string(parts[0])
        set_cleaned_artist(song, library_artists, self.artist_db, source=parts[0])
        song.tag_collection.set_item(TITLE, parts[1].strip())
        print(library_artists, parts[1].strip())
        return True


class InferArtistFromTitleByRule(TagRule):
    def __init__(self, artist_names, artist_db):
        self.artist_names = artist_names
        self.artist_db = artist_db

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        if not title or ' by ' not in title.lower():
            return False
        parts = re.split('\\sby\\s', title, flags=re.IGNORECASE)
        if len(parts) == 2:
            track, artist_guess = (parts[0].strip(), parts[1].strip())
            library_artists = extract_artists_from_string(artist_guess)
            if any(a.lower() in self.artist_names for a in library_artists):
                set_cleaned_artist(song, library_artists, self.artist_db, source=artist_guess)
                song.tag_collection.set_item(TITLE, track)
                return True
        return False


class InferArtistFromTitleSingleDashRule(TagRule):
    def __init__(self, artist_names, artist_db, festival_helper=None):
        self.artist_names = artist_names
        self.artist_db = artist_db
        self.festival_helper = festival_helper

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        title = normalise_pipes(title)
        if not title or title.count(' - ') != 1:
            return False
        left, right = [s.strip() for s in title.split(' - ', 1)]
        # An edition that once slipped into library_artists would otherwise match
        # itself exactly here and keep the artist and the title swapped forever.
        # A fuzzy match is enough for that: "Thunderdome 2006" scores 0.81 against
        # a plain "Thunderdome", so neither side may be an event.
        left_is_event = looks_like_an_event(left, self.festival_helper)
        right_is_event = looks_like_an_event(right, self.festival_helper)
        if left_is_event and right_is_event:
            return False
        matches_left = (
            [] if left_is_event else [a for a in extract_artists_from_string(left) if a.lower() in self.artist_names]
        )
        matches_right = (
            [] if right_is_event else [a for a in extract_artists_from_string(right) if a.lower() in self.artist_names]
        )
        if matches_left:
            set_cleaned_artist(song, extract_artists_from_string(left), self.artist_db, source=left)
            song.tag_collection.set_item(TITLE, right)
            return True
        if matches_right:
            set_cleaned_artist(song, extract_artists_from_string(right), self.artist_db, source=right)
            song.tag_collection.set_item(TITLE, left)
            return True
        fuzzy_left = extract_artists_from_string(left)
        fuzzy_right = extract_artists_from_string(right)
        fuzzy_match_left = (
            []
            if left_is_event
            else [a for a in fuzzy_left if has_close_artist(a.lower(), self.artist_names, cutoff=0.75)]
        )
        fuzzy_match_right = (
            []
            if right_is_event
            else [a for a in fuzzy_right if has_close_artist(a.lower(), self.artist_names, cutoff=0.75)]
        )
        if fuzzy_match_left:
            set_cleaned_artist(song, fuzzy_match_left, self.artist_db, source=left)
            song.tag_collection.set_item(TITLE, right)
            return True
        if fuzzy_match_right:
            set_cleaned_artist(song, fuzzy_match_right, self.artist_db, source=right)
            song.tag_collection.set_item(TITLE, left)
            return True
        return False


class InferArtistFromTitleMultiDashRule(TagRule):
    def __init__(self, artist_names, artist_db, genre_names, festival_helper=None):
        self.artist_names = artist_names
        self.artist_db = artist_db
        self.genre_names = genre_names
        self.festival_helper = festival_helper

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        title = self._clean_raw_title(title)
        if not title or ' - ' not in title:
            return False
        segments = [s.strip() for s in title.split(' - ') if s.strip()]
        if len(segments) < 3:
            return False
        best_match_index, best_artists = self._find_best_match(segments)
        if best_match_index == -1:
            return False
        set_cleaned_artist(song, best_artists, self.artist_db, source=segments[best_match_index])
        remaining_segments = [seg for i, seg in enumerate(segments) if i != best_match_index]
        title = ' - '.join(remaining_segments)
        song.tag_collection.set_item(TITLE, title)
        return True

    def _clean_raw_title(self, title):
        if not title:
            return ''
        title = normalise_pipes(title)
        title = title.replace(' I ', ' - ')
        title = title.replace(' warmup mix ', ' warmup mix - ')
        title = title.replace(' warm-up mix ', ' warm-up mix - ')
        return title

    def _find_best_match(self, segments):
        best_match_index = -1
        best_match_score = 0.0
        best_artists = []
        for idx, segment in enumerate(segments):
            filtered_artists = self._get_filtered_artists(segment)
            for artist in filtered_artists:
                lowered = artist.lower()
                if lowered in self.genre_names:
                    continue
                if looks_like_an_event(artist, self.festival_helper):
                    continue
                matches = get_close_matches(lowered, self.artist_names, n=1, cutoff=0.6)
                if matches:
                    score = SequenceMatcher(None, lowered, matches[0]).ratio() + 0.05
                    if score > best_match_score:
                        best_match_score = score
                        best_match_index = idx
                        best_artists = filtered_artists
        return (best_match_index, best_artists)

    def _get_filtered_artists(self, segment):
        library_artists = extract_artists_from_string(segment)
        filtered_artists = []
        for artist in library_artists:
            cleaned = re.sub('\\s*[\\(\\[\\{<][^()\\[\\]{}<>]*[\\)\\]\\}>]', '', artist).strip()
            if not cleaned or cleaned.lower() in {
                'live',
                'dj set',
                'set',
                'remix',
                'edit',
                'extended mix',
                'mix',
                'version',
            }:
                continue
            filtered_artists.append(cleaned)
        return filtered_artists


class InferArtistFromFirstSegmentFallbackRule(TagRule):
    def __init__(self, artist_db, festival_helper=None, ignored_names=None):
        self.artist_db = artist_db
        self.festival_helper = festival_helper
        self.ignored_names = ignored_names or set()

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        title = normalise_pipes(title)
        if not title or ' - ' not in title:
            return False
        parts = [s.strip() for s in title.split(' - ', 1)]
        if len(parts) == 2:
            artist_candidate, title_part = parts
            # This is the last guess before giving up, so it must not guess an
            # event: that is how "Thunderdome 2025" became an artist.
            if looks_like_an_event(artist_candidate, self.festival_helper):
                return False
            # Nor a name the curation has already rejected. This rule matches nothing, so it is
            # the one place a promo marker can still be taken for an artist on its own.
            if any(name.lower() in self.ignored_names for name in extract_artists_from_string(artist_candidate)):
                return False
            if artist_candidate:
                set_cleaned_artist(song, artist_candidate, self.artist_db, source=artist_candidate)
                song.tag_collection.set_item(TITLE, title_part)
                return True
        return False


class InferArtistFromTitleFallbackRule(TagRule):
    def __init__(self, rules_ignored_artists):
        self.rules_ignored_artists = {a.lower() for a in rules_ignored_artists}

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        if not title:
            return False
        folder_artist = song.path().split(os.sep)[-2].strip().lower()
        if folder_artist in self.rules_ignored_artists:
            return False
        if ' - ' in title:
            parts = [s.strip() for s in title.split(' - ', 1)]
            if len(parts) == 2:
                first_segment, rest = parts
                if first_segment.lower() == folder_artist:
                    song.tag_collection.set_item(TITLE, rest)
                    return True
        return False


class InferArtistFromPresentsOrColonRule(TagRule):
    def __init__(self, artist_db):
        self.artist_db = artist_db
        self.artist_names = frozenset(artist_index(artist_db))

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        if not title:
            return False
        match = re.search('\\b([A-Za-z0-9 &\\-_]+?)\\s*(presents:|presents\\b|:)', title, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if has_close_artist(candidate.lower(), self.artist_names, cutoff=0.7):
                set_cleaned_artist(song, candidate, self.artist_db, source=candidate)
                new_title = title[match.end() :].strip()
                song.tag_collection.set_item(TITLE, new_title)
                return True
        return False
