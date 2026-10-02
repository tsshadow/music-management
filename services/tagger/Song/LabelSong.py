from datetime import date

from services.common.config_store import ConfigStore as Settings
from services.common.import_queue import ImportQueue
from services.tagger.constants import CATALOG_NUMBER, COPYRIGHT, PUBLISHER
from services.tagger.Song import LabelPath, rule_stack
from services.tagger.Song.BaseSong import BaseSong
from services.tagger.Song.rules.DropQueuePlaceholderRule import DropQueuePlaceholderRule

s = Settings()


class LabelSong(BaseSong):
    """A release in the label tree: publisher, catalogue number and copyright come from its path.

    The path may name no label -- `__Free&None`, the import queue, a release folder in the wrong
    place -- and then the publisher is written empty rather than as that folder's name (bug report
    146). The importer's Mover reaches this class directly for every release it files, whatever
    folder `rules_catid_label` sends it to, so the check lives in `LabelPath.split`, not in the
    callers.
    """

    def __init__(self, path):
        super().__init__(path)
        publisher, release_folder = LabelPath.split(path, s.eps_folder_path, s.delimiter, ImportQueue.from_settings(s))
        self._publisher = str(publisher)
        self._catalog_number = str(LabelPath.catalog_number(release_folder))
        #: The day the release first reached the import queue, set by the importer's Mover; the
        #: release-date ladder's last rung before the year (InferReleaseDateFromNfoRule).
        self.arrival_date: date | None = None

    def parse(self):
        # First: a copyright of "__TODO (2021)" left by bug report 030 is emptied here, so the
        # check below recomputes it from the publisher this path actually names.
        DropQueuePlaceholderRule().apply(self)
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
