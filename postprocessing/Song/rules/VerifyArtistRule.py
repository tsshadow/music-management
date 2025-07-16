import logging
import re
from collections import defaultdict
from typing import Optional

from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.Song.rules.TagResult import TagResult, TagResultType
from postprocessing.Song.rules.ExternalArtistLookup import ExternalArtistLookup
from postprocessing.constants import ARTIST

logger = logging.getLogger(__name__)


class VerifyArtistRule(TagRule):
    """Validate and normalize the ARTIST tag of a song."""

    PLACEHOLDERS = [
        "unknown artist",
        "various artists",
        "on toxic sickness radio",
        "live at",
        "year anniversary",
        "hardcore special",
    ]

    NUMERIC_ONLY = re.compile(r"^#?\d+[.)]?$")
    NUMERIC_PREFIX = re.compile(r"^#?\d{1,3}[.)\s-]+")
    INVALID_START = re.compile(r"^[#\-\(\*'\"\[]+")

    def __init__(self, artist_db: Optional[TableHelper] = None, lookup: Optional[ExternalArtistLookup] = None):
        self.artist_db = artist_db or TableHelper("artists", "name")
        self.lookup = lookup or ExternalArtistLookup()
        self.seen_counts: defaultdict[str, int] = defaultdict(int)

    def _heuristic_check(self, name: str) -> tuple[str, bool, bool]:
        """Return (clean_name, changed, invalid)"""
        original = name
        name = name.strip()

        # numeric only
        if self.NUMERIC_ONLY.fullmatch(name):
            return name, False, True

        # numeric prefix
        prefix = self.NUMERIC_PREFIX.match(name)
        if prefix:
            name = name[prefix.end():].strip()
            if not name:
                return original, False, True
            return name, True, False

        # start with strange chars
        cleaned = self.INVALID_START.sub("", name).strip()
        if cleaned != name:
            name = cleaned
            if not name:
                return original, False, True
            changed = True
        else:
            changed = False

        # unbalanced brackets/quotes
        if name.count("(") != name.count(")"):
            name = name.replace("(", "").replace(")", "")
            changed = True
        if name.count("[") != name.count("]"):
            name = name.replace("[", "").replace("]", "")
            changed = True
        if name.count('"') % 2 == 1:
            name = name.replace('"', "")
            changed = True
        if name.count("'") % 2 == 1:
            name = name.replace("'", "")
            changed = True

        # length/composition checks
        if len(name) <= 2 and not re.search(r"[A-Za-z]", name):
            return original, False, True
        if not re.search(r"[A-Za-z]", name):
            return original, False, True

        # placeholders
        lower = name.lower()
        for frag in self.PLACEHOLDERS:
            if frag in lower:
                return original, False, True

        return name, changed, False

    def apply(self, song) -> TagResult:
        artist = song.artist()
        if not artist:
            return TagResult(None, TagResultType.UNKNOWN)

        tag_item = song.tag_collection.get_item(ARTIST)
        self.seen_counts[artist.lower()] += 1

        # Step 1: check database
        if self.artist_db.exists(artist):
            canonical = self.artist_db.get(artist)
            if canonical != artist:
                tag_item.remove(artist)
                tag_item.add(canonical)
                logger.info("Updated artist casing '%s' -> '%s'", artist, canonical)
                return TagResult(canonical, TagResultType.UPDATED)
            return TagResult(artist, TagResultType.VALID)

        # Step 2: external lookup
        if self.lookup.is_known_artist(artist):
            insert = getattr(self.artist_db, "insert_if_not_exists", None)
            if callable(insert):
                insert(artist)
            else:
                if not self.artist_db.exists(artist):
                    self.artist_db.add(artist)
            logger.info("Added artist '%s' from external lookup", artist)
            return TagResult(artist, TagResultType.VALID)

        # Step 3: heuristics
        cleaned, changed, invalid = self._heuristic_check(artist)
        if invalid:
            tag_item.remove(artist)
            logger.info("Ignored invalid artist '%s'", artist)
            return TagResult(artist, TagResultType.IGNORED)
        if changed and cleaned != artist:
            tag_item.remove(artist)
            tag_item.add(cleaned)
            logger.info("Cleaned artist '%s' -> '%s'", artist, cleaned)
            return TagResult(cleaned, TagResultType.UPDATED)

        return TagResult(artist, TagResultType.UNKNOWN)
