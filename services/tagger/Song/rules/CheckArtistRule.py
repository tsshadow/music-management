from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.common.Helpers.TrustedArtistHelper import TrustedArtistHelper
from services.tagger.constants import ARTIST
from services.tagger.Song.rules.TagRule import TagRule


class CheckArtistRule(TagRule):
    """Normalises artist names against library_artists and rules_ignored_artists."""

    def __init__(self, artist_db=None, ignored_db=None):
        from services.common.Helpers.Cache import databaseHelpers

        self.artist_table = artist_db or databaseHelpers.get('library_artists') or TrustedArtistHelper()
        self.ignored_table = (
            ignored_db
            or databaseHelpers.get('rules_ignored_artists')
            or FilterTableHelper('rules_ignored_artists', 'name', 'corrected_name', follow_chains=True)
        )

    def apply(self, song) -> None:
        """Swap each artist for its canonical or corrected spelling, in place.

        Iterates over a snapshot: the list `library_artists()` returns is the tag's live
        value, and mutating it mid-loop skipped values and re-appended corrections at the
        end -- which demoted the primary artist and changed the order again on every pass.
        """
        if not song.library_artists():
            return
        tag_item = song.tag_collection.get_item(ARTIST)
        for raw in list(song.library_artists()):
            name = raw.strip()
            if not name:
                continue
            if self.artist_table.exists(name):
                canonical = self.artist_table.get(name)
                if canonical and canonical != name:
                    tag_item.replace(raw, canonical)
                continue
            corrected = self.ignored_table.get_corrected(name)
            if corrected:
                print(f"↪️ Corrigeer '{name}' naar '{corrected}'")
                tag_item.replace(raw, corrected)
                continue
            if self.ignored_table.exists(name):
                print(f'🧹 Verwijder foutieve artiest zonder correctie: {name}')
                tag_item.remove(raw)
                continue
