import os
import re
from difflib import SequenceMatcher, get_close_matches

from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.common.Helpers.TableHelper import TableHelper
from services.tagger.constants import ARTIST, ARTIST_REGEX_NON_CAPTURING, ORIGINAL_TITLE, TITLE
from services.tagger.Song.rules.TagRule import TagRule

# "Thunderdome 2025", "Emporium 2025", "Snakepit 2024": an edition, never an artist.
YEAR_SUFFIX_PATTERN = re.compile(r'\b(19[89]\d|20[0-4]\d)\s*$')
PIPE_CHARACTERS = ('｜', '|')

def extract_artists_from_string(part: str) -> list[str]:
    return [a.strip() for a in re.split(ARTIST_REGEX_NON_CAPTURING, part) if a.strip()]

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

def set_cleaned_artist(song, library_artists: str | list[str], artist_db=None) -> bool:
    if isinstance(library_artists, str):
        library_artists = [library_artists]
    blacklist = {'live', 'dj set', 'set', 'remix', 'edit', 'extended mix', 'mix', 'version', 'remix edit', 'remix pro', 'a1 ', 'a2 ', 'b1 ', 'b2 '}
    artist_db = artist_db or TableHelper('library_artists', 'name')
    all_artists = {name.lower(): name for name in artist_db.get_all_values() if name}
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
    return True

class InferArtistFromTitleRule(TagRule):

    def __init__(self, artist_db=None, ignored_db: FilterTableHelper=None, genre_db: FilterTableHelper=None, festival_helper=None):
        from services.common.Helpers.Cache import databaseHelpers
        self.artist_db = artist_db or databaseHelpers.get('library_artists') or TableHelper('library_artists', 'name')
        self.festival_helper = festival_helper or databaseHelpers.get('festivalHelper')
        all_names = self.artist_db.get_all_values()
        artist_names = {name.lower() for name in all_names if name}
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
        self.rules = [InferArtistFromPresentsOrColonRule(self.artist_db), InferArtistFromTitleAtRule(ignored_names, self.artist_db), InferArtistFromEventPrefixRule(artist_names, self.artist_db, all_genres, self.festival_helper), InferArtistFromTitleByRule(artist_names, self.artist_db), InferArtistFromTitleDotRule(artist_names, self.artist_db), InferArtistFromTitleSingleDashRule(artist_names, self.artist_db, self.festival_helper), InferArtistFromTitleMultiDashRule(artist_names, self.artist_db, all_genres, self.festival_helper), InferArtistFromFirstSegmentFallbackRule(self.artist_db, self.festival_helper), InferArtistFromTitleFallbackRule(ignored_names)]

    def apply(self, song):
        if not song.tag_collection.has_item(ORIGINAL_TITLE):
            song.tag_collection.set_item(ORIGINAL_TITLE, song.tag_collection.get_item_as_string(TITLE))
        for rule in self.rules:
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
        for pipe in PIPE_CHARACTERS:
            title = title.replace(pipe, '-')
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
        set_cleaned_artist(song, candidates, self.artist_db)
        song.tag_collection.set_item(TITLE, event)
        return True

    def _looks_like_artists(self, candidates):
        if any(c.lower() in self.blocked_names for c in candidates):
            return False
        if any(c.lower() in self.artist_names for c in candidates):
            return True
        if any(get_close_matches(c.lower(), self.artist_names, n=1, cutoff=0.75) for c in candidates):
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
        set_cleaned_artist(song, library_artists, self.artist_db)
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
        set_cleaned_artist(song, library_artists, self.artist_db)
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
                set_cleaned_artist(song, library_artists, self.artist_db)
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
        title = title.replace('|', '-')
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
        matches_left = [] if left_is_event else [a for a in extract_artists_from_string(left) if a.lower() in self.artist_names]
        matches_right = [] if right_is_event else [a for a in extract_artists_from_string(right) if a.lower() in self.artist_names]
        if matches_left:
            set_cleaned_artist(song, extract_artists_from_string(left), self.artist_db)
            song.tag_collection.set_item(TITLE, right)
            return True
        if matches_right:
            set_cleaned_artist(song, extract_artists_from_string(right), self.artist_db)
            song.tag_collection.set_item(TITLE, left)
            return True
        fuzzy_left = extract_artists_from_string(left)
        fuzzy_right = extract_artists_from_string(right)
        fuzzy_match_left = [] if left_is_event else [a for a in fuzzy_left if get_close_matches(a.lower(), self.artist_names, n=1, cutoff=0.75)]
        fuzzy_match_right = [] if right_is_event else [a for a in fuzzy_right if get_close_matches(a.lower(), self.artist_names, n=1, cutoff=0.75)]
        if fuzzy_match_left:
            set_cleaned_artist(song, fuzzy_match_left, self.artist_db)
            song.tag_collection.set_item(TITLE, right)
            return True
        if fuzzy_match_right:
            set_cleaned_artist(song, fuzzy_match_right, self.artist_db)
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
        set_cleaned_artist(song, best_artists, self.artist_db)
        remaining_segments = [seg for i, seg in enumerate(segments) if i != best_match_index]
        title = ' - '.join(remaining_segments)
        song.tag_collection.set_item(TITLE, title)
        return True

    def _clean_raw_title(self, title):
        if not title:
            return ''
        title = title.replace('|', '-')
        title = title.replace('｜', '-')
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
            if not cleaned or cleaned.lower() in {'live', 'dj set', 'set', 'remix', 'edit', 'extended mix', 'mix', 'version'}:
                continue
            filtered_artists.append(cleaned)
        return filtered_artists

class InferArtistFromFirstSegmentFallbackRule(TagRule):

    def __init__(self, artist_db, festival_helper=None):
        self.artist_db = artist_db
        self.festival_helper = festival_helper

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        title = title.replace('|', '-')
        if not title or ' - ' not in title:
            return False
        parts = [s.strip() for s in title.split(' - ', 1)]
        if len(parts) == 2:
            artist_candidate, title_part = parts
            # This is the last guess before giving up, so it must not guess an
            # event: that is how "Thunderdome 2025" became an artist.
            if looks_like_an_event(artist_candidate, self.festival_helper):
                return False
            if artist_candidate:
                set_cleaned_artist(song, artist_candidate, self.artist_db)
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
        self.artist_names = {name.lower() for name in artist_db.get_all_values() if name}

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(ORIGINAL_TITLE)
        if not title:
            return False
        match = re.search('\\b([A-Za-z0-9 &\\-_]+?)\\s*(presents:|presents\\b|:)', title, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if get_close_matches(candidate.lower(), self.artist_names, n=1, cutoff=0.7):
                set_cleaned_artist(song, candidate, self.artist_db)
                new_title = title[match.end():].strip()
                song.tag_collection.set_item(TITLE, new_title)
                return True
        return False