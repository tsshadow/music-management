from services.common.Helpers.FestivalHelper import FestivalHelper
from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.common.Helpers.GenreRulesHelper import GenreRulesHelper
from services.common.Helpers.HelperRegistry import reload_helpers
from services.common.Helpers.LookupTableHelper import LookupTableHelper
from services.common.Helpers.PodcastHelper import PodcastHelper
from services.common.Helpers.TableHelper import TableHelper

databaseHelpers = {
    'library_artists': TableHelper('library_artists', 'name'),
    'rules_ignored_artists': FilterTableHelper('rules_ignored_artists', 'name', 'corrected_name', follow_chains=True),
    'rules_genres': FilterTableHelper('rules_genres', 'name', 'corrected_genre'),
    'rules_ignored_genres': TableHelper('rules_ignored_genres', 'name'),
    'genre_rules': GenreRulesHelper(),
    'artistGenreHelper': LookupTableHelper('rules_artist_genre', 'artist', 'genre'),
    'labelGenreHelper': LookupTableHelper('rules_label_genre', 'label', 'genre'),
    'subgenreHelper': LookupTableHelper('rules_subgenre_hierarchy', 'subgenre', 'genre'),
    'rules_genre_backlog': TableHelper('rules_genre_backlog', 'genre'),
    'sceneGroupDateFormatHelper': LookupTableHelper('rules_scene_group_date_format', 'scene_group', 'date_format'),
    'festivalHelper': FestivalHelper(),
    'podcastHelper': PodcastHelper(),
}


def reload(key: str | None = None) -> list[str]:
    """Rebuild one preloaded helper from the database, or all of them.

    Call this straight after writing to a table one of these helpers reads, so the
    reply the caller gets already reflects the write. Other processes that share the
    table (importer, downloader) catch up on their own; see
    `LookupTableHelper.STALE_AFTER_SECONDS`.
    """
    return reload_helpers(databaseHelpers, key)
