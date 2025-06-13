import re
from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import TITLE, GENRE
from postprocessing.Song.Helpers.TableHelper import TableHelper

class InferGenreFromTitleRule(TagRule):
    def __init__(self, genre_db=None, dryrun=True, dryrun_output_path="genre_matches.txt"):
        self.genre_db = genre_db or TableHelper("genres", "genre")
        self.dryrun = dryrun
        self.dryrun_output_path = dryrun_output_path

        all_genres = self.genre_db.get_all_values()
        self.genre_set = set(g.lower() for g in all_genres if g)

        # Compile regex patterns for each genre
        self.genre_patterns = {
            genre: re.compile(rf"\b{re.escape(genre)}\b", flags=re.IGNORECASE)
            for genre in self.genre_set
        }

        if self.dryrun:
            self._output_file = open(self.dryrun_output_path, "w", encoding="utf-8")
        else:
            self._output_file = None

    def apply(self, song) -> bool:
        title = song.tag_collection.get_item_as_string(TITLE)
        if not title:
            return False

        found = False
        for genre, pattern in self.genre_patterns.items():
            if pattern.search(title):
                canonical = self.genre_db.get_canonical(genre)

                if self.dryrun:
                    line = f"{canonical} - {song.path}\n"
                    self._output_file.write(line)
                else:
                    song.tag_collection.add(GENRE, canonical)

                found = True

        return found

    def __del__(self):
        if self._output_file:
            self._output_file.close()
