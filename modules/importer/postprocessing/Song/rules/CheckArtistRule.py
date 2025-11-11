from postprocessing.Song.Helpers.FilterTableHelper import FilterTableHelper
from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import ARTIST


class CheckArtistRule(TagRule):
    def __init__(self, artist_db=None, ignored_db=None):
        self.artist_table = artist_db or TableHelper("artists", "name")
        self.ignored_table = ignored_db or FilterTableHelper("ignored_artists", "name", "corrected_name")

    def apply(self, song) -> None:
        if not song.artists():
            return

        tag_item = song.tag_collection.get_item(ARTIST)

        for name in song.artists():
            name = name.strip()
            if not name:
                continue

            # ✅ Artiest bekend → canonical taggen
            if self.artist_table.exists(name):
                canonical = self.artist_table.get(name)
                if canonical != name:
                    tag_item.add(canonical)
                    tag_item.remove(name)
                continue

            # ↪️ Corrigeer indien mogelijk
            corrected = self.ignored_table.get_corrected(name)
            if corrected:
                print(f"↪️ Corrigeer '{name}' naar '{corrected}'")
                tag_item.remove(name)
                tag_item.add(corrected)
                continue

            # 🧹 Verwijder artiest zonder correctie
            if self.ignored_table.exists(name):
                print(f"🧹 Verwijder foutieve artiest zonder correctie: {name}")
                tag_item.remove(name)
                continue

            # 🚫 Onbekend: doe niets (andere rule moet dit opvangen)
