import logging
import re

from postprocessing.Song.Helpers.FilterTableHelper import FilterTableHelper
from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import TITLE, ARTIST, REMIXER


class InferRemixerFromTitleRule(TagRule):
    """
    Haalt remixer/edit-artiesten uit de titel (bijv. '(XYZ Remix)') en voegt ze toe
    aan het ARTIST-veld én het aparte REMIXERS-tagveld (nieuw).
    Nieuwe artiesten kunnen toegevoegd of genegeerd worden via gebruikersprompt.
    """

    BRACKET_RE = re.compile(r"\(([^()]*)\)")
    SUFFIX_CLEANUP_FULL = re.compile(
        r"\s*\b("
        r"album|bootleg|cinematic|climax|cut|dub|dubstep|edit|extended|hardcore|hardstyle|instrumental|kick|live|mix|non vocal|non-vocal|nostalgia|old school|original|pro remix|radio|refix|remastered|remix|re-kick|uptempo|version|vip|vocal|"
        r"\d{4}|2k\d{2}"
        r")\b\s*$",
        re.IGNORECASE
    )
    SUFFIX_CLEANUP_SIMPLE = re.compile(r"\s*\b(edit|remix|refix|bootleg)\b\s*$", re.IGNORECASE)

    def __init__(self, artist_db=None, ignored_db=None, ask_for_missing: bool = False):
        self.artist_db = artist_db or TableHelper("artists", "name")
        self.ignored_db = ignored_db or FilterTableHelper("ignored_artists", "name", "corrected_name")
        self.ask_for_missing = ask_for_missing

    def _clean_artist_name(self, name: str) -> str:
        name = re.sub(r"['’]s\s+(remix|edit|refix|version|bootleg|mix|vip)\b", r" \1", name, flags=re.IGNORECASE)
        while True:
            new_name = re.sub(self.SUFFIX_CLEANUP_FULL, "", name).strip()
            if new_name == name:
                return new_name
            name = new_name

    def _clean_suffix_only(self, name: str) -> str:
        while True:
            new_name = re.sub(self.SUFFIX_CLEANUP_SIMPLE, "", name).strip()
            if new_name == name:
                return new_name
            name = new_name

    def apply(self, song) -> None:
        title = song.tag_collection.get_item_as_string(TITLE)
        if not title:
            return

        bracket_segments = self.BRACKET_RE.findall(title)
        for segment in bracket_segments:
            if not re.search(r"(edit|remix|refix|bootleg|remix edit)", segment, re.IGNORECASE):
                continue

            for raw_artist in song.split_artists( self._clean_suffix_only(segment)):
                artist = self._clean_artist_name(raw_artist)

                if not artist.strip() or artist.strip().isdigit():
                    continue

                exists = self.artist_db.exists(artist)
                canonical = self.artist_db.get(artist)
                # Check ignore list first
                if not exists:
                    if self.ignored_db.exists(artist):
                        corrected = self.ignored_db.get_corrected(artist)
                        song.tag_collection.get_item(ARTIST).remove(artist)
                        song.tag_collection.get_item(REMIXER).remove(artist)

                        if corrected:
                            canonical = corrected
                    elif self.ask_for_missing:
                        user_input = input(f"Is '{artist}' een valide artiest? (j/n/[corrected]) ").strip()
                        if user_input.lower() == "j":
                            self.artist_db.add(artist)
                            canonical = artist
                            logging.info(f"'{artist}' toegevoegd aan artiestendatabase.")
                        elif user_input.lower() == "n":
                            self.ignored_db.add(artist)
                            logging.info(f"'{artist}' toegevoegd aan ignore-lijst.")
                            continue
                        elif user_input:
                            self.ignored_db.add(artist, user_input)
                            logging.info(f"'{artist}' toegevoegd aan ignore-lijst met correctie '{user_input}'.")
                            canonical = user_input
                        else:
                            logging.info(f"'{artist}' werd genegeerd.")
                            continue
                    else:
                        logging.info(f"'{artist}' niet gevonden in database of ignore-lijst, overslaan.")
                        continue

                artist_tag = song.tag_collection.get_item(ARTIST)
                if canonical not in artist_tag.to_array() and canonical is not None and len(canonical) > 1:
                    artist_tag.add(canonical)
                    artist_tag.regex()
                    artist_tag.deduplicate()

                if song.tag_collection.has_item(REMIXER)  and canonical is not None and len(canonical) > 1:
                    remixer_tag = song.tag_collection.get_item(REMIXER)
                    if canonical not in remixer_tag.to_array():
                        remixer_tag.add(canonical)
                        remixer_tag.regex()
                        remixer_tag.deduplicate()
