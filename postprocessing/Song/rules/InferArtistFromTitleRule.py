import os
import re
from difflib import get_close_matches
from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import TITLE, ARTIST, ARTIST_REGEX_NON_CAPTURING

def extract_artists_from_string(part: str) -> list[str]:
    return [a.strip() for a in re.split(ARTIST_REGEX_NON_CAPTURING, part) if a.strip()]

import re
from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.constants import ARTIST

def set_cleaned_artist(song, artists: str | list[str], artist_db=None) -> bool:
    if isinstance(artists, str):
        artists = [artists]

    blacklist = {
        "live", "dj set", "set", "remix", "edit", "extended mix", "mix", "version"
    }

    artist_db = artist_db or TableHelper("artists", "name")
    all_artists = {name.lower(): name for name in artist_db.get_all_values() if name}

    cleaned = []
    for a in artists:
        raw = a.strip()

        # Remove anything in parentheses: e.g. "Artist (LIVE)" -> "Artist"
        base = re.sub(r"\s*\([^)]*\)", "", raw).strip()

        # Strip trailing blacklist suffixes (e.g. "LUNAKORPZ LIVE" -> "LUNAKORPZ")
        words = base.split()
        while words and words[-1].lower() in blacklist:
            words.pop()
        base = " ".join(words).strip()

        if not base:
            continue

        corrected = all_artists.get(base.lower(), base)
        cleaned.append(corrected)

    if not cleaned:
        return False

    print(cleaned)
    song.tag_collection.set_item(ARTIST, ";".join(cleaned))
    return True




class InferArtistFromTitleRule(TagRule):
    def __init__(self, artist_db=None, ignored_artists=None):
        self.artist_db = artist_db or TableHelper("artists", "name")
        all_names = self.artist_db.get_all_values()
        artist_names = set(name.lower() for name in all_names if name)
        ignored_artists = ignored_artists or []

        self.rules = [
            InferArtistFromTitleAtRule(ignored_artists, self.artist_db),
            InferArtistFromTitleByRule(artist_names, self.artist_db),
            InferArtistFromTitleSingleDashRule(artist_names, self.artist_db),
            InferArtistFromTitleMultiDashRule(artist_names, self.artist_db),
            InferArtistFromFirstSegmentFallbackRule(self.artist_db),
            InferArtistFromTitleFallbackRule(ignored_artists),
        ]

    def apply(self, song):
        for rule in self.rules:
            if rule.apply(song):
                print(f"[InferArtistFromTitle] Applied rule: {rule.__class__.__name__} on '{song.path()}'")
                return

class InferArtistFromTitleAtRule(TagRule):
    def __init__(self, ignored_artists, artist_db):
        self.ignored_artists = set(a.lower() for a in ignored_artists)
        self.artist_db = artist_db

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(TITLE)
        if not title:
            return False
        folder_artist = song.path().split(os.sep)[-2].lower()
        if folder_artist in self.ignored_artists:
            return False
        if folder_artist and folder_artist in title.lower() and " @ " in title:
            parts = title.split(" @ ", 1)
            if folder_artist in parts[0].lower():
                artists = extract_artists_from_string(parts[0])
                set_cleaned_artist(song, artists, self.artist_db)
                song.tag_collection.set_item(TITLE, parts[1].strip())
                return True
        return False

class InferArtistFromTitleByRule(TagRule):
    def __init__(self, artist_names, artist_db):
        self.artist_names = artist_names
        self.artist_db = artist_db

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(TITLE)
        if not title or " by " not in title.lower():
            return False
        parts = re.split(r"\sby\s", title, flags=re.IGNORECASE)
        if len(parts) == 2:
            track, artist_guess = parts[0].strip(), parts[1].strip()
            artists = extract_artists_from_string(artist_guess)
            if any(a.lower() in self.artist_names for a in artists):
                set_cleaned_artist(song, artists, self.artist_db)
                song.tag_collection.set_item(TITLE, track)
                return True
        return False

class InferArtistFromTitleSingleDashRule(TagRule):
    def __init__(self, artist_names, artist_db):
        self.artist_names = artist_names
        self.artist_db = artist_db

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(TITLE)
        title = title.replace('|','-')
        title = title.replace(' I ',' - ')
        if not title or title.count(" - ") != 1:
            return False
        left, right = [s.strip() for s in title.split(" - ", 1)]
        matches_left = [a for a in extract_artists_from_string(left) if a.lower() in self.artist_names]
        matches_right = [a for a in extract_artists_from_string(right) if a.lower() in self.artist_names]

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

        fuzzy_match_left = [a for a in fuzzy_left if get_close_matches(a.lower(), self.artist_names, n=1, cutoff=0.75)]
        fuzzy_match_right = [a for a in fuzzy_right if get_close_matches(a.lower(), self.artist_names, n=1, cutoff=0.75)]

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
    def __init__(self, artist_names, artist_db):
        self.artist_names = artist_names
        self.artist_db = artist_db

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(TITLE)
        title = title.replace('|','-')
        title = title.replace(' I ',' - ')
        if not title or " - " not in title:
            return False
        segments = [s.strip() for s in title.split(" - ") if s.strip()]
        if len(segments) < 3:
            return False

        best_match_index = -1
        best_match_score = 0.0
        best_artists = []

        for idx, segment in enumerate(segments):
            artists = extract_artists_from_string(segment)

            # Clean artists up front
            filtered_artists = []
            for artist in artists:
                cleaned = re.sub(r"\s*\([^)]*\)", "", artist).strip()
                if not cleaned or cleaned.lower() in {"live", "dj set", "set", "remix", "edit", "extended mix", "mix",
                                                      "version"}:
                    continue
                filtered_artists.append(cleaned)

            for artist in filtered_artists:
                matches = get_close_matches(artist.lower(), self.artist_names, n=1, cutoff=0.6)
                if matches:
                    from difflib import SequenceMatcher
                    score = SequenceMatcher(None, artist.lower(), matches[0]).ratio()
                    if score > best_match_score:
                        best_match_score = score
                        best_match_index = idx
                        best_artists = filtered_artists

        if best_match_index == -1:
            return False

        set_cleaned_artist(song, best_artists, self.artist_db)
        remaining_segments = [seg for i, seg in enumerate(segments) if i != best_match_index]
        song.tag_collection.set_item(TITLE, " - ".join(remaining_segments))
        return True

class InferArtistFromFirstSegmentFallbackRule(TagRule):
    def __init__(self, artist_db):
        self.artist_db = artist_db

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(TITLE)
        title = title.replace('|','-')
        title = title.replace(' I ',' - ')
        if not title or " - " not in title:
            return False
        parts = [s.strip() for s in title.split(" - ", 1)]
        if len(parts) == 2:
            artist_candidate, title_part = parts
            if artist_candidate:
                set_cleaned_artist(song, artist_candidate, self.artist_db)
                song.tag_collection.set_item(TITLE, title_part)
                return True
        return False

class InferArtistFromTitleFallbackRule(TagRule):
    def __init__(self, ignored_artists):
        self.ignored_artists = set(a.lower() for a in ignored_artists)

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(TITLE)
        if not title:
            return False
        folder_artist = song.path().split(os.sep)[-2].strip().lower()
        if folder_artist in self.ignored_artists:
            return False
        if " - " in title:
            parts = [s.strip() for s in title.split(" - ", 1)]
            if len(parts) == 2:
                first_segment, rest = parts
                if first_segment.lower() == folder_artist:
                    song.tag_collection.set_item(TITLE, rest)
                    return True
        return False
