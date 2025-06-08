import logging
import re

from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import TITLE, ARTIST, REMIXERS


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

    def __init__(self, artist_db=None, ignored_db=None):
        from postprocessing.Song.Helpers.LookupTableHelper import LookupTableHelper
        self.artist_db = artist_db or TableHelper("artists", "name")
        self.ignored_db = ignored_db or TableHelper("ignored_artists", "name")

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
        original_artist = song.tag_collection.get_item_as_string(ARTIST)
        if not title:
            return

        bracket_segments = self.BRACKET_RE.findall(title)
        for segment in bracket_segments:
            if not re.search(r"(edit|remix|refix|bootleg)", segment, re.IGNORECASE):
                continue

            cleaned_segment = self._clean_suffix_only(segment)
            for raw_artist in song.split_artists(cleaned_segment):
                artist = self._clean_artist_name(raw_artist)

                if raw_artist != artist:
                    song.tag_collection.get_item(ARTIST).remove(raw_artist)

                if not artist.strip() or artist.strip().isdigit():
                    continue

                canonical = self.artist_db.get_canonical(artist)
                if not canonical:
                    logging.info(f"Geen canonical gevonden voor '{artist}', overslaan.")
                    continue

                if self.ignored_db.exists(canonical):
                    song.tag_collection.get_item(ARTIST).remove(canonical)
                    logging.info(f"Remixer '{canonical}' staat op ignore-lijst, verwijderd.")
                    continue

                if not self.artist_db.exists(canonical):
                    response = input(
                        f"Remixer '{canonical}' voor\n`{original_artist} - {title}`\n niet gevonden. Toevoegen? [y/N/i voor negeren]: "
                    ).strip().lower()

                    if response == "i":
                        self.ignored_db.add(canonical)
                        logging.info(f"Remixer '{canonical}' toegevoegd aan ignore-tabel.")
                        song.tag_collection.get_item(ARTIST).remove(canonical)
                        continue
                    if response != "y":
                        logging.info(f"Remixer '{canonical}' overgeslagen.")
                        continue

                    self.artist_db.add(canonical)
                    logging.info(f"Remixer '{canonical}' toegevoegd aan artists-tabel.")

                # Voeg toe aan ARTIST (indien nodig)
                artist_tag = song.tag_collection.get_item(ARTIST)
                if canonical not in artist_tag.to_array():
                    before = artist_tag.to_string()
                    changed = artist_tag.changed

                    artist_tag.add(canonical)
                    artist_tag.regex()
                    artist_tag.special_recapitalize()
                    artist_tag.deduplicate()

                    if before == artist_tag.to_string():
                        artist_tag.changed = changed

                    logging.info(f"Toegevoegd aan ARTIST: {canonical}")

                # Voeg toe aan REMIXERS (ook als al in ARTIST)
                # remixer_tag = song.tag_collection.get_item(REMIXERS)
                # if canonical not in remixer_tag.to_array():
                #     remixer_tag.add(canonical)
                #     remixer_tag.regex()
                #     remixer_tag.special_recapitalize()
                #     remixer_tag.deduplicate()
                #     logging.info(f"Toegevoegd aan REMIXERS: {canonical}")
