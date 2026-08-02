import logging

from services.common.Helpers.GenreRulesHelper import UNKNOWN, GenreRulesHelper
from services.tagger.constants import GENRE
from services.tagger.Song.rules.TagRule import TagRule

logger = logging.getLogger(__name__)


class ResolveGenreRule(TagRule):
    """The only gate between inferred genres and the library.

    Replaces CleanAndFilterGenreRule plus AddMissingGenreToDatabaseRule, which ran
    back to back: the first pushed every unknown genre into the backlog and the
    second accepted anything present in that backlog, so an unknown genre was
    registered and approved within the same pass. One lookup and one decision per
    genre removes that ordering dependency instead of patching it.
    """

    def __init__(self, helper=None):
        self.helper = helper or GenreRulesHelper()

    def apply(self, song, filter_genres=True):
        if not song.tag_collection.has_item(GENRE):
            return
        genre_tag = song.tag_collection.get_item(GENRE)
        genre_tag.regex()
        genre_tag.recapitalize()
        genre_tag.strip()
        genre_tag.sort()
        if not filter_genres:
            return
        current_genres = genre_tag.to_array()
        resolved = []
        for genre in current_genres:
            # A composite such as 'Hardstyle/Hardcore' becomes two genres before
            # anything is decided, so each half is judged on its own and the
            # combination never reaches the curation queue.
            for part in self.helper.split_composite(genre):
                decision = self.helper.resolve(part)
                if decision.state == UNKNOWN:
                    self.helper.record_unknown(part)
                resolved.extend(decision.values)
        resolved = sorted(set(resolved))
        if resolved != current_genres:
            logger.info('Resolved genres %s to %s for %s', current_genres, resolved, song.path())
            genre_tag.set(resolved)
