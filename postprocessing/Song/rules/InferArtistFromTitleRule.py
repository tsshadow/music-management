import os
import re
from difflib import get_close_matches
from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import TITLE, ARTIST

ARTIST_REGEX = r"(?i)\s(?:&|，|aka|and|b2b|b3b|feat\.?|featuring|features|ft\.?|invite|invites|meets|pres\.?|presenting|versus|vs\.?|with|x|\+|,|et)\s|,\s|，\s"

def extract_artists_from_string(part: str) -> list[str]:
    return [a.strip() for a in re.split(ARTIST_REGEX, part) if a.strip()]

class InferArtistFromTitleRule(TagRule):
    def __init__(self, artist_db=None, ignored_artists=None):
        self.artist_db = artist_db or TableHelper("artists", "name")
        all_names = self.artist_db.get_all_values()
        self.artist_names = set(name.lower() for name in all_names if name)
        self.ignored_artists = set(a.lower() for a in (ignored_artists or []))

    def apply(self, song):
        artist = song.tag_collection.get_item_as_string(ARTIST)
        title = song.tag_collection.get_item_as_string(TITLE)
        if not title:
            return

        p = song.path()
        folder_artist = p.split(os.sep)[-2].lower()
        if folder_artist in self.ignored_artists:
            return

        # STEP 1: Handle "Artist @ Event"
        if folder_artist and folder_artist in title.lower():
            if " @ " in title:
                parts = title.split(" @ ", 1)
                if folder_artist in parts[0].lower():
                    artists = extract_artists_from_string(parts[0])
                    song.tag_collection.add(ARTIST, ";".join(artists))
                    song.tag_collection.set_item(TITLE, parts[1].strip())
                    return

        # STEP 2: Handle "Track by Artist"
        if " by " in title.lower():
            parts = re.split(r"\sby\s", title, flags=re.IGNORECASE)
            if len(parts) == 2:
                track, artist_guess = parts[0].strip(), parts[1].strip()
                artists = extract_artists_from_string(artist_guess)
                if any(a.lower() in self.artist_names for a in artists):
                    song.tag_collection.add(ARTIST, ";".join(artists))
                    song.tag_collection.set_item(TITLE, track)
                    return

        # STEP 3: Advanced " - " split logic
        if " - " in title:
            parts = title.split(" - ", 1)
            if len(parts) == 2:
                left, right = parts[0].strip(), parts[1].strip()

                # Try exact matches
                matches_left = [a for a in extract_artists_from_string(left) if a.lower() in self.artist_names]
                matches_right = [a for a in extract_artists_from_string(right) if a.lower() in self.artist_names]

                if matches_left:
                    all_left = extract_artists_from_string(left)
                    song.tag_collection.set_item(ARTIST, ";".join(all_left))
                    song.tag_collection.set_item(TITLE, right)
                    return
                elif matches_right:
                    all_right = extract_artists_from_string(right)
                    song.tag_collection.set_item(ARTIST, ";".join(all_right))
                    song.tag_collection.set_item(TITLE, left)
                    return

                # Try fuzzy matches
                fuzzy_left = extract_artists_from_string(left)
                fuzzy_right = extract_artists_from_string(right)

                fuzzy_match_left = [
                    a for a in fuzzy_left
                    if get_close_matches(a.lower(), self.artist_names, n=1, cutoff=0.75)
                ]
                fuzzy_match_right = [
                    a for a in fuzzy_right
                    if get_close_matches(a.lower(), self.artist_names, n=1, cutoff=0.75)
                ]

                if fuzzy_match_left:
                    song.tag_collection.add(ARTIST, ";".join(fuzzy_match_left))
                    song.tag_collection.set_item(TITLE, right)
                    return
                elif fuzzy_match_right:
                    song.tag_collection.add(ARTIST, ";".join(fuzzy_match_right))
                    song.tag_collection.set_item(TITLE, left)
                    return

                # Final fallback: take left part as artist
                if left:
                    song.tag_collection.add(ARTIST, left)
                    song.tag_collection.set_item(TITLE, right)
                    return

        # STEP 4: Fallback - title starts with folder artist
        if folder_artist and " - " in title:
            parts = title.split(" - ", 1)
            if parts[0].strip().lower() == folder_artist:
                song.tag_collection.set_item(TITLE, parts[1].strip())
                return

        if folder_artist and " @ " in title:
            parts = title.split(" @ ", 1)
            if parts[0].strip().lower() == folder_artist:
                song.tag_collection.set_item(TITLE, parts[1].strip())
