import logging
import re
from collections import defaultdict
from typing import Optional
from services.common.Helpers.TableHelper import TableHelper
from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.Song.rules.TagResult import TagResult, TagResultType
from services.tagger.Song.rules.ExternalArtistLookup import ExternalArtistLookup
from services.tagger.constants import ARTIST
logger = logging.getLogger(__name__)

class VerifyArtistRule(TagRule):
    """Validate and normalize the ARTIST tag of a song."""
    NUMERIC_ONLY = re.compile('^#?\\d+[.)]?$')
    NUMERIC_PREFIX = re.compile('^#?\\d{1,3}[.)\\s-]+')
    INVALID_START = re.compile('^[&#\\-\\(\\*\'\\"\\[]+')

    def __init__(self, artist_db: Optional[TableHelper]=None, lookup: Optional[ExternalArtistLookup]=None):
        self.artist_db = artist_db or TableHelper('library_artists', 'name')
        self.lookup = lookup or ExternalArtistLookup()
        self.seen_counts: defaultdict[str, int] = defaultdict(int)

    def _heuristic_check(self, name: str) -> tuple[str, bool, bool]:
        """Return (clean_name, changed, invalid)"""
        original = name
        name = name.strip()
        if self.NUMERIC_ONLY.fullmatch(name):
            return (name, False, True)
        prefix = self.NUMERIC_PREFIX.match(name)
        if prefix:
            name = name[prefix.end():].strip()
            if not name:
                return (original, False, True)
            return (name, True, False)
        cleaned = self.INVALID_START.sub('', name).strip()
        changed = False
        if cleaned != name:
            name = cleaned
            if not name:
                return (original, False, True)
            changed = True
        if name.count('(') != name.count(')'):
            name = name.replace('(', ';').replace(')', ';')
            changed = True
        if name.count('[') != name.count(']'):
            name = name.replace('[', ';').replace(']', ';')
            changed = True
        if name.count('"') % 2 == 1:
            name = name.replace('"', '')
            changed = True
        is_invalid = len(name) <= 2 and (not re.search('[A-Za-z]', name)) or not re.search('[A-Za-z]', name)
        if is_invalid:
            return (original, False, True)
        return (name, changed, False)

    def apply(self, song) -> TagResult:
        artist = song.artist()
        if not artist:
            return TagResult(None, TagResultType.UNKNOWN)
        tag_item = song.tag_collection.get_item(ARTIST)
        self.seen_counts[artist.lower()] += 1
        if self.artist_db.exists(artist):
            canonical = self.artist_db.get(artist)
            if canonical != artist:
                tag_item.remove(artist)
                tag_item.add(canonical)
                logger.info("Updated artist casing '%s' -> '%s'", artist, canonical)
                return TagResult(canonical, TagResultType.UPDATED)
            return TagResult(artist, TagResultType.VALID)
        if self.lookup.is_known_artist(artist):
            if hasattr(self.artist_db, 'insert_if_not_exists'):
                self.artist_db.insert_if_not_exists(artist)
            elif not self.artist_db.exists(artist):
                self.artist_db.add(artist)
            logger.info("Added artist '%s' from external lookup", artist)
            return TagResult(artist, TagResultType.VALID)
        if artist.lower() in {'unknown artist', 'various artists'}:
            tag_item.remove(artist)
            return TagResult(artist, TagResultType.IGNORED)
        cleaned, changed, invalid = self._heuristic_check(artist)
        res_type = TagResultType.UNKNOWN
        res_val = artist
        if invalid:
            tag_item.remove(artist)
            logger.info("Ignored invalid artist '%s'", artist)
            res_type = TagResultType.IGNORED
        elif changed and cleaned != artist:
            tag_item.remove(artist)
            tag_item.add(cleaned)
            logger.info("Cleaned artist '%s' -> '%s'", artist, cleaned)
            res_type = TagResultType.UPDATED
            res_val = cleaned
        return TagResult(res_val, res_type)