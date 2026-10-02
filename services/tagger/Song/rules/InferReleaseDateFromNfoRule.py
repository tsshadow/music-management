import logging
import os
import re
from datetime import date

from services.common.Helpers.LookupTableHelper import LookupTableHelper
from services.common.release_nfo import links as nfo_links
from services.tagger.constants import BARCODE, DATE, DATE_SOURCE, ORIGINAL_DATE
from services.tagger.Song import NfoDate
from services.tagger.Song.rules.TagRule import TagRule

#: Where a release date came from, written to DATE_SOURCE, ranked best first (lower is better).
#: The owner's weighting: exact 100%, a day off 75%, the same week 50%, the year only 10%.
SOURCE_RANKS = {
    'deezer': 10,
    'nfo-street': 20,
    'nfo-release': 20,
    'tag': 25,
    'nfo-rip': 30,
    'arrival': 40,
}

_NFO_SOURCES = {'street': 'nfo-street', 'release': 'nfo-release', 'rip': 'nfo-rip'}


class InferReleaseDateFromNfoRule(TagRule):
    """
    Gives a label release the best release date the evidence allows, and says where it came from.

    Label rips arrive tagged with a year and nothing more, which is too coarse to sort by release
    date: LMS orders "recently released" on `COALESCE(original_date, date)` as text, so `2026`
    sorts below every dated 2026 track. The ladder, best first (docs/designs/release-info-enrichment/):

      1. `deezer`      -- the release date of the album the .nfo links, from `release_store_lookups`
                          (filled by the importer; this rule never goes over the network);
      2. `nfo-street` / `nfo-release` -- a street, release, store or retail date line in the .nfo;
      3. `tag`         -- the file's own DATE at day precision;
      4. `nfo-rip`     -- the rip date (`Rip.date`, `Rls.date`, `Date`), usually within a week;
      5. `arrival`     -- the day the release first reached the import queue, set by the importer,
                          only when it falls in the release's own year;
      6. the year only, as before: nothing is written.

    The year in the release directory's name guards every rung, so a rip date cannot redate a 1995
    vinyl release. The result goes to ORIGINALDATE and its rung to DATE_SOURCE. A better rung
    replaces a worse one on a later retag; a worse one never replaces a better one. A
    day-precision date without DATE_SOURCE that equals the .nfo's date or the file's DATE is this
    rule's from before the ladder, and counts as that rung (`infer_source`); it gets DATE_SOURCE
    even when nothing better exists. Any other date without DATE_SOURCE is a person's and is never
    replaced. The album's UPC goes to BARCODE when the file has none: it is not a
    catalogue number and is never used as one.
    """

    def __init__(self, format_helper=None, store=None):
        self.format_helper = format_helper or LookupTableHelper(
            'rules_scene_group_date_format', 'scene_group', 'date_format'
        )
        self._store = store

    @property
    def store(self):
        """The store-lookup cache, read-only here; created on first use."""
        if self._store is None:
            from services.common.store_lookup import StoreCache

            self._store = StoreCache()
        return self._store

    def apply(self, song):
        tags = song.tag_collection
        current = tags.get_item_as_string(ORIGINAL_DATE)
        stamped = tags.get_item_as_string(DATE_SOURCE).strip()
        current_source = stamped
        if _is_day_precision(current) and current_source not in SOURCE_RANKS:
            current_source = ''

        directory = os.path.dirname(song.path())
        dirname = os.path.basename(directory)
        text = NfoDate.read_nfo(directory) or ''
        expected_year = NfoDate.dirname_year(dirname) or _year_of(tags.get_item_as_string(DATE))

        album = self._album(text)
        found = self._candidates(song, text, dirname, expected_year, album)
        current_rank = None
        if _is_day_precision(current):
            current_source = current_source or infer_source(current, found) or ''
            current_rank = SOURCE_RANKS.get(current_source)
            if current_rank is None:
                return

        if album is not None and album.found and album.upc and not tags.get_item_as_string(BARCODE).strip():
            tags.set_item(BARCODE, album.upc)

        if not found:
            return
        value, source = min(found, key=lambda item: SOURCE_RANKS[item[1]])
        rank = SOURCE_RANKS[source]
        if current_rank is not None and not (rank < current_rank or (source == current_source and value != current)):
            if current_source != stamped:
                # The pre-ladder rule's date, still the best there is: only say where it came from.
                tags.set_item(DATE_SOURCE, current_source)
            return
        if value == current and source == stamped:
            return
        logging.info('Release date for %s resolved to %s (%s)', song.path(), value, source)
        tags.set_item(ORIGINAL_DATE, value)
        tags.set_item(DATE_SOURCE, source)

    def _album(self, text):
        """The cached store album the .nfo links, or None."""
        link = next((link for link in nfo_links(text) if link.store == 'deezer'), None)
        if link is None:
            return None
        try:
            return self.store.lookup(link)
        except Exception as exc:  # noqa: BLE001 - the ladder simply skips the rung
            logging.debug('No store answer for %s: %s', link.url, exc)
            return None

    def _candidates(self, song, text, dirname, expected_year, album):
        """Every `(date, source)` the evidence offers, in no particular order."""
        found = []
        store_date = album.full_date if album is not None and album.found else None
        if store_date and (expected_year is None or int(store_date[:4]) == expected_year):
            found.append((store_date, 'deezer'))
        if text:
            group = NfoDate.scene_group(dirname)
            formats = self.format_helper.get(group) if group else []
            kind, resolved = NfoDate.resolve(text, dirname, formats[0] if formats else None)
            if resolved is not None:
                found.append((resolved.isoformat(), _NFO_SOURCES.get(kind, 'nfo-rip')))
        from_tag = from_date_tag(song.tag_collection.get_item_as_string(DATE))
        if from_tag and (expected_year is None or int(from_tag[:4]) == expected_year):
            found.append((from_tag, 'tag'))
        arrival = getattr(song, 'arrival_date', None)
        if isinstance(arrival, date) and expected_year is not None and arrival.year == expected_year:
            found.append((arrival.isoformat(), 'arrival'))
        return found


def infer_source(current, found):
    """The rung a full date without DATE_SOURCE came from, or None when it is not this rule's.

    Before the ladder this rule wrote the .nfo's date, else the file's own full DATE, and named no
    source. A date that still equals one of those is that rung's; any other date is a person's and
    is never replaced.
    """
    day = (current or '').strip()[:10]
    return next((source for value, source in found if value == day and source not in ('deezer', 'arrival')), None)


def _is_day_precision(value):
    return len(re.sub(r'\D', '', value or '')) >= 8


def _year_of(value):
    match = re.match(r'\s*(\d{4})', value or '')
    return int(match.group(1)) if match else None


def from_date_tag(value):
    """A day-precision DATE tag as a partial date string, or None.

    Same evidence, stored in the field that means "this edition" rather than "original release", so it
    is worth promoting when nothing better is known.
    """
    digits = re.sub(r'\D', '', (value or '')[:10])
    if len(digits) < 8:
        return None
    candidate = f'{digits[0:4]}-{digits[4:6]}-{digits[6:8]}'
    return candidate if NfoDate.resolve_token(candidate) else None
