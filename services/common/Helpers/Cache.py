from typing import Any

from services.common.Helpers.ChannelLinkHelper import ChannelLinkHelper
from services.common.Helpers.FestivalHelper import FestivalHelper
from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.common.Helpers.GenreRulesHelper import GenreRulesHelper
from services.common.Helpers.HelperRegistry import reload_helpers
from services.common.Helpers.LookupTableHelper import LookupTableHelper
from services.common.Helpers.PodcastHelper import PodcastHelper
from services.common.Helpers.TableHelper import TableHelper
from services.common.Helpers.TrustedArtistHelper import TrustedArtistHelper

# Any: a registry of unrelated helper classes, each looked up by name.
databaseHelpers: dict[str, Any] = {
    # Only the names the tagger may trust (approved, or grandfathered at wiring time),
    # not every name the scanner inserted; see TrustedArtistHelper.
    'library_artists': TrustedArtistHelper(),
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
    # The label/artist a download's channel is linked to; see docs/designs/channel-links.
    'channelLinkHelper': ChannelLinkHelper(),
}


def reload(key: str | None = None) -> list[str]:
    """Rebuild one preloaded helper from the database, or all of them.

    Call this straight after writing to a table one of these helpers reads, so the
    reply the caller gets already reflects the write. Other processes that share the
    table (importer, downloader) catch up on their own; see
    `LookupTableHelper.STALE_AFTER_SECONDS`.
    """
    return reload_helpers(databaseHelpers, key)
