"""The import queue's name is emptied out of publisher and copyright (bug reports 030 and 087)."""

import unittest

from services.common.import_queue import ImportQueue
from services.tagger.constants import COPYRIGHT, PUBLISHER
from services.tagger.Song.rules.DropQueuePlaceholderRule import DropQueuePlaceholderRule
from services.tagger.Song.Tag import Tag


class _Collection:
    """has_item/get_item_as_string/set_item over real Tags, so change tracking is the real one."""

    def __init__(self, **tags):
        self.tags = {name: Tag(name, value) for name, value in tags.items()}

    def has_item(self, name):
        return name in self.tags

    def get_item_as_string(self, name):
        return self.tags[name].to_string()

    def set_item(self, name, value):
        self.tags[name].set(value)


class _Song:
    def __init__(self, **tags):
        self.tag_collection = _Collection(**tags)


class DropQueuePlaceholderRuleTest(unittest.TestCase):
    rule = DropQueuePlaceholderRule(ImportQueue('/mnt/music/EPs/__TODO'))

    def test_a_placeholder_publisher_and_copyright_are_emptied(self):
        song = _Song(**{PUBLISHER: '__TODO', COPYRIGHT: '__TODO (2021)'})

        self.rule.apply(song)

        self.assertEqual('', song.tag_collection.get_item_as_string(PUBLISHER))
        self.assertEqual('', song.tag_collection.get_item_as_string(COPYRIGHT))
        # Emptied, not deleted: an emptied Tag reports a change, which is what makes
        # BaseSong.save_file write the file and drop the frame.
        self.assertTrue(song.tag_collection.tags[PUBLISHER].has_changes())

    def test_a_real_label_is_left_alone(self):
        song = _Song(**{PUBLISHER: 'Scantraxx', COPYRIGHT: 'Scantraxx (2021)'})

        self.rule.apply(song)

        self.assertEqual('Scantraxx', song.tag_collection.get_item_as_string(PUBLISHER))
        self.assertFalse(song.tag_collection.tags[COPYRIGHT].has_changes())

    def test_the_old_name_is_dropped_after_the_queue_moved(self):
        song = _Song(**{PUBLISHER: '__todo'})

        DropQueuePlaceholderRule(ImportQueue('/mnt/music/import')).apply(song)

        self.assertEqual('', song.tag_collection.get_item_as_string(PUBLISHER))

    def test_missing_tags_are_not_created(self):
        song = _Song()
        self.rule.apply(song)
        self.assertEqual({}, song.tag_collection.tags)


if __name__ == '__main__':
    unittest.main()
