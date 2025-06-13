from postprocessing.Song.Helpers.FilterTableHelper import FilterTableHelper
from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.Song.rules.TagRule import TagRule


class AddMissingGenreToDatabaseRule(TagRule):
    def __init__(self, genre_db=None, ignored_db=None):
        self.genre_table = genre_db or TableHelper("genres", "genre")
        self.ignored_table = ignored_db or FilterTableHelper("ignored_genres", "name", "corrected_name")

    def apply(self, song) -> None:
        if not song.genres():
            return

        for genre in song.genres():
            genre = genre.strip()
            if not genre:
                continue

            # ✅ Staat al in 'genres' → overslaan
            if self.genre_table.exists(genre):
                continue

            # ↪️ Staat al in 'ignored_genres' → overslaan
            if self.ignored_table.exists(genre):
                continue

            try:
                user_input = input(
                    f"{song.path()}\nIs '{genre}' een juist genre? [y/N] voor:\n"
                    f"{song.artist()} - {song.title()}\n"
                    f"(Laat leeg of 'n' voor nee, of vul juist genre in): "
                ).strip()
            except EOFError:
                user_input = ""

            if user_input.lower() == "y":
                self.genre_table.add(genre)
                print(f"✅ Genre toegevoegd: {genre}")
            elif user_input == "" or user_input.lower() == "n":
                self.ignored_table.add(genre)
                print(f"❌ Genre genegeerd: {genre}")
            else:
                self.ignored_table.add(genre, user_input)
                print(f"✅ Gecorrigeerd genre toegevoegd: {user_input}")
