import logging
from services.common.Helpers.GenreRulesHelper import GenreRulesHelper, UNKNOWN
from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.constants import GENRE
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
            decision = self.helper.resolve(genre)
            if decision.state == UNKNOWN:
                self.helper.record_unknown(genre)
            if decision.value:
                resolved.append(decision.value)
        resolved = sorted(set(resolved))
        if resolved != current_genres:
            logger.info('Resolved genres %s to %s for %s', current_genres, resolved, song.path())
            genre_tag.set(resolved)
