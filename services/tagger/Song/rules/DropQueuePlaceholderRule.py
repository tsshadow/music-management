from services.common.import_queue import ImportQueue
from services.tagger.constants import COPYRIGHT, PUBLISHER
from services.tagger.Song.rules.TagRule import TagRule


class DropQueuePlaceholderRule(TagRule):
    """Empties a publisher or copyright that holds the import queue's name instead of a label.

    Before 2026-07-28 the tagger ran LabelSong over releases still waiting in the import queue and
    wrote the queue's own folder name (`__TODO`) in as their publisher, and a copyright of
    "__TODO (<year>)" computed from it (bug report 030). Nothing ever took it out again: GenericSong
    does not touch the publisher, and LabelSong overwrites the publisher but only computes a
    copyright when there is none -- so a moved release kept its poisoned copyright for good.

    Run first by GenericSong and LabelSong, before either computes a copyright, so an emptied value
    is recomputed from the real publisher (or left empty) in the same pass. Setting '' rather than
    deleting is what makes `BaseSong.save_file` notice the change and drop the tag from the file.
    The repair that queues the affected files is services/tagger/todo_label_repair.py.

    "Placeholder" is `ImportQueue.is_placeholder_publisher`: besides the queue's name it covers an
    underscore folder's name (`__Free&None`) and a release folder's name (bug report 146), so a
    release filed in `__Free&None` loses that publisher on its next retag instead of keeping it.
    """

    def __init__(self, queue: ImportQueue | None = None):
        self._queue = queue

    def apply(self, song) -> None:
        queue = self._queue or ImportQueue.from_settings()
        collection = song.tag_collection
        if collection.has_item(PUBLISHER) and queue.is_placeholder_publisher(collection.get_item_as_string(PUBLISHER)):
            collection.set_item(PUBLISHER, '')
        if collection.has_item(COPYRIGHT) and queue.is_placeholder_copyright(collection.get_item_as_string(COPYRIGHT)):
            collection.set_item(COPYRIGHT, '')
