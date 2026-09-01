import logging
import os
import re

from services.common.Helpers.LookupTableHelper import LookupTableHelper
from services.tagger.constants import DATE, ORIGINAL_DATE
from services.tagger.Song import NfoDate
from services.tagger.Song.rules.TagRule import TagRule


class InferReleaseDateFromNfoRule(TagRule):
    """
    Fills in the original release date from the scene NFO that ships with a label release.

    Label rips arrive with a year and nothing more, which is too coarse to sort by release date or to
    match an anniversary against. The NFO in the release directory usually states the exact date, and
    the year in the directory name is the guard that stops a rip date from redating old music.

    Only ever fills in what is missing or coarser. A date already at day precision is left alone.
    """

    def __init__(self, format_helper=None):
        self.format_helper = format_helper or LookupTableHelper(
            'rules_scene_group_date_format', 'scene_group', 'date_format'
        )

    def apply(self, song):
        if _is_day_precision(song.tag_collection.get_item_as_string(ORIGINAL_DATE)):
            return

        directory = os.path.dirname(song.path())
        dirname = os.path.basename(directory)
        resolved = self._from_nfo(directory, dirname)
        if resolved is None:
            resolved = _from_date_tag(song.tag_collection.get_item_as_string(DATE))
        if resolved is None:
            return

        logging.info('Release date for %s resolved to %s', song.path(), resolved)
        song.tag_collection.set_item(ORIGINAL_DATE, resolved)

    def _from_nfo(self, directory, dirname):
        """The NFO's date as a partial date string, or None."""
        text = NfoDate.read_nfo(directory)
        if not text:
            return None
        group = NfoDate.scene_group(dirname)
        formats = self.format_helper.get(group) if group else []
        _kind, resolved = NfoDate.resolve(text, dirname, formats[0] if formats else None)
        return resolved.isoformat() if resolved else None


def _is_day_precision(value):
    return len(re.sub(r'\D', '', value or '')) >= 8


def _from_date_tag(value):
    """A day-precision DATE tag as a partial date string, or None.

    Same evidence, stored in the field that means "this edition" rather than "original release", so it
    is worth promoting when the NFO has nothing to say.
    """
    digits = re.sub(r'\D', '', (value or '')[:10])
    if len(digits) < 8:
        return None
    candidate = f'{digits[0:4]}-{digits[4:6]}-{digits[6:8]}'
    return candidate if NfoDate.resolve_token(candidate) else None
