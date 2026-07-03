from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.common.Helpers.TableHelper import TableHelper
from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.constants import ARTIST


class CheckArtistRule(TagRule):

    def __init__(self, artist_db=None, ignored_db=None):
        from services.common.Helpers.Cache import databaseHelpers
        self.artist_table = artist_db or databaseHelpers.get('library_artists') or TableHelper('library_artists', 'name')
        self.ignored_table = ignored_db or databaseHelpers.get('rules_ignored_artists') or FilterTableHelper('rules_ignored_artists', 'name', 'corrected_name')

    def apply(self, song) -> None:
        if not song.library_artists():
            return
        tag_item = song.tag_collection.get_item(ARTIST)
        for name in song.library_artists():
            name = name.strip()
            if not name:
                continue
            if self.artist_table.exists(name):
                canonical = self.artist_table.get(name)
                if canonical != name:
                    tag_item.add(canonical)
                    tag_item.remove(name)
                continue
            corrected = self.ignored_table.get_corrected(name)
            if corrected:
                print(f"↪️ Corrigeer '{name}' naar '{corrected}'")
                tag_item.remove(name)
                tag_item.add(corrected)
                continue
            if self.ignored_table.exists(name):
                print(f'🧹 Verwijder foutieve artiest zonder correctie: {name}')
                tag_item.remove(name)
                continue