from services.common.config_store import ConfigStore as Settings
from services.tagger.constants import COPYRIGHT
from services.tagger.Song import rule_stack
from services.tagger.Song.BaseSong import BaseSong
from services.tagger.Song.rules.DropQueuePlaceholderRule import DropQueuePlaceholderRule

s = Settings()


class GenericSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        self._catalog_number = None

    def parse(self):
        # First, so a copyright computed below never falls back to a poisoned publisher.
        DropQueuePlaceholderRule().apply(self)
        if not self.copyright() and self.calculate_copyright():
            self.tag_collection.set_item(COPYRIGHT, self.calculate_copyright())
        self.sort_genres()
        # Built once per tagging round, not per file; see rule_stack.
        self.rules.extend(rule_stack.rules_for(rule_stack.GENERIC))
        super().parse()

    def calculate_copyright(self):
        album_artist = self.album_artist()
        date = self.date()
        year = str(date)[0:4]
        if album_artist:
            if date:
                return album_artist + ' (' + year + ')'
            return self.publisher()
        return None
