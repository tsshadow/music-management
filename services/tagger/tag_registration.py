"""The custom tag names mutagen has to be taught, in one place.

Most of what the tagger writes is standard vocabulary: artist, album, genre. A handful
of names are not, and for those mutagen refuses the key outright unless it has been
registered first -- an ID3 file has no `podcast` frame, so `EasyID3` maps the name onto
a `TXXX` frame with that description, and only for names it was told about.

This lived twice, as two hand-kept blocks in `tagger.py` and in `Song/BaseSong.py`, and
the two drifted: `podcast` and `podcast_episode` were added to every tag map when the
podcast rule shipped and to neither block. Writing one on an MP3 then raised
`EasyID3KeyError`, which aborted the whole file's save -- and the parallel worker
returned that error rather than logging it, so the only visible symptom was a podcast
browse that stayed empty. One list, imported by both, is what keeps that from repeating.
"""

from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4Tags

from services.tagger.constants import (
    BARCODE,
    DATE_SOURCE,
    FESTIVAL,
    ORIGINAL_ARTIST,
    ORIGINAL_TITLE,
    PARSED,
    PODCAST,
    PODCAST_EPISODE,
    PUBLISHER,
    RATING,
    REMIXER,
)

# Every tag name the tagger writes that no format knows on its own. The name is also the
# key `BaseSong.set_tag` writes on the MP3 path, so it has to match `MP3Tags`.
CUSTOM_TAG_KEYS = (
    PUBLISHER,
    RATING,
    PARSED,
    FESTIVAL,
    REMIXER,
    ORIGINAL_TITLE,
    ORIGINAL_ARTIST,
    PODCAST,
    PODCAST_EPISODE,
    DATE_SOURCE,
    BARCODE,
)

# The rating frame that already exists in the library is `TXXX:RATING`. Registering the
# name against a lower-case description would write a second frame beside it instead of
# updating it, so this one keeps its own spelling. ORIGINAL_ARTIST gets the same treatment
# so its MP3 description matches WAVTags' `TXXX:ORIGINAL_ARTIST` casing.
# DATE_SOURCE and BARCODE match WAVTags' upper-case descriptions too; BARCODE is also the
# description EasyID3's own `barcode` key uses, so re-registering it changes nothing.
ID3_DESCRIPTIONS = {
    RATING: 'RATING',
    ORIGINAL_ARTIST: 'ORIGINAL_ARTIST',
    DATE_SOURCE: 'DATE_SOURCE',
    BARCODE: 'BARCODE',
}


def register_custom_tag_keys():
    """Teach EasyID3 and EasyMP4 the names above. Safe to call more than once."""
    for key in CUSTOM_TAG_KEYS:
        EasyID3.RegisterTXXXKey(key, ID3_DESCRIPTIONS.get(key, key))
        EasyMP4Tags.RegisterTextKey(key, key)
