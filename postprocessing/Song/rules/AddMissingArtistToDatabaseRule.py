from postprocessing.Song.Helpers.FilterTableHelper import FilterTableHelper
from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.Song.rules.TagRule import TagRule


class AddMissingArtistToDatabaseRule(TagRule):
    def __init__(self, artist_db=None, ignored_db=None):
        self.artist_table = artist_db or TableHelper("artists", "name")
        self.ignored_table = ignored_db or FilterTableHelper("ignored_artists", "name", "corrected_name")

    def apply(self, song) -> None:
        if not song.artists():
            return

        for name in song.artists():
            name = name.strip()
            if not name:
                continue

            # ✅ Staat al in 'artists' → overslaan
            if self.artist_table.exists(name):
                continue

            # ↪️ Staat al in 'ignored_artists' → overslaan
            if self.ignored_table.exists(name):
                continue

            # ❓ Vraag gebruiker om bevestiging of correctie
            try:
                user_input = input(
                    f"{song.path()}\nIs '{name}' een juiste artiest? [y/N] voor:\n"
                    f"{song.artist()} - {song.title()}\n"
                    f"(Laat leeg of 'n' voor nee, of vul juiste artiest in): "
                ).strip()
            except EOFError:
                user_input = ""

            if user_input.lower() == "y":
                self.artist_table.add(name)
                print(f"✅ Artiest toegevoegd: {name}")
            elif user_input == "" or user_input.lower() == "n":
                self.ignored_table.add(name)
                print(f"❌ Artiest genegeerd: {name}")
            else:
                self.ignored_table.add(name, user_input)
                print(f"✅ Gecorrigeerde artiest toegevoegd: {user_input}")
