from services.common.config_store import ConfigStore as Settings
from services.tagger.constants import CATALOG_NUMBER, COPYRIGHT, PUBLISHER
from services.tagger.Song import LabelPath, rule_stack
from services.tagger.Song.BaseSong import BaseSong

s = Settings()


class LabelSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        publisher, release_folder = LabelPath.split(path, s.eps_folder_path, s.delimiter)
        self._publisher = str(publisher)
        self._catalog_number = str(LabelPath.catalog_number(release_folder))

    def parse(self):
        self.tag_collection.set_item(PUBLISHER, self._publisher)
        if self._catalog_number:
            self.tag_collection.set_item(CATALOG_NUMBER, self._catalog_number)
        if not self.copyright():
            c = self.calculate_copyright()
            if c:
                self.tag_collection.set_item(COPYRIGHT, c)
        # Built once per tagging round, not per file; see rule_stack.
        self.rules.extend(rule_stack.rules_for(rule_stack.LABEL))
        super().parse()

    def calculate_copyright(self):
        publisher = self.publisher()
        date = self.date()
        if publisher:
            if date:
                return f'{publisher} ({str(date)[:4]})'
            return publisher
        return None
