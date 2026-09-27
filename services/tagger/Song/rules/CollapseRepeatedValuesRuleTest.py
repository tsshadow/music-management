"""The repair of a title or credit the old `ORIG` atom defect repeated (bug report 117).

The values below are the shapes found on production on 2026-09-27: the repeated derived value
many times over, plus the downloaded title once.
"""

import unittest
from unittest.mock import MagicMock

from services.tagger.constants import ARTIST, ORIGINAL_ARTIST, ORIGINAL_TITLE, TITLE
from services.tagger.Song.rules.CollapseRepeatedValuesRule import CollapseRepeatedValuesRule
from services.tagger.Song.Tag import Tag
from services.tagger.Song.TagCollection import TagCollection


def song_with(**tags):
    """A song stub whose tag collection is real, holding `tags` as read from a file."""
    collection = TagCollection(None)
    for key, value in tags.items():
        collection.tags[key] = Tag(key, value)
    song = MagicMock()
    song.tag_collection = collection
    return song


class CollapseRepeatedValuesRuleTest(unittest.TestCase):
    def test_the_crypton_file_gets_its_downloaded_title_back(self):
        song = song_with(
            **{
                ORIGINAL_TITLE: ';'.join(["UNTIL IT'S GONE"] * 241 + ["Crypton - UNTIL IT'S GONE"]),
                TITLE: ';'.join(["UNTIL IT'S GONE"] * 241 + ['Crypton']),
            }
        )
        CollapseRepeatedValuesRule().apply(song)
        tags = song.tag_collection
        self.assertEqual(tags.get_item_as_array(ORIGINAL_TITLE), ["Crypton - UNTIL IT'S GONE"])
        self.assertEqual(tags.get_item_as_array(TITLE), ["UNTIL IT'S GONE"])
        self.assertTrue(tags.get_item(ORIGINAL_TITLE).has_changes())
        self.assertTrue(tags.get_item(TITLE).has_changes())

    def test_the_101barz_file_keeps_the_pipes_of_its_original(self):
        song = song_with(
            **{
                ORIGINAL_TITLE: ';'.join(
                    ['Throwback Sessie'] * 100
                    + ['Throwback Sessie - 101Barz', 'The Opposites | Throwback Sessie | 101Barz']
                ),
            }
        )
        CollapseRepeatedValuesRule().apply(song)
        self.assertEqual(
            song.tag_collection.get_item_as_array(ORIGINAL_TITLE), ['The Opposites | Throwback Sessie | 101Barz']
        )

    def test_a_repeated_display_credit_collapses_to_its_usual_value(self):
        song = song_with(**{ORIGINAL_ARTIST: ';'.join(['Karma Outdoor 2025'] * 181)})
        CollapseRepeatedValuesRule().apply(song)
        self.assertEqual(song.tag_collection.get_item_as_array(ORIGINAL_ARTIST), ['Karma Outdoor 2025'])

    def test_distinct_values_are_left_alone(self):
        # A title that legitimately contains ';' splits into distinct values -- not the defect.
        song = song_with(**{ORIGINAL_TITLE: 'Angerfist - Raise Your Fist;Remix', TITLE: 'Raise Your Fist;Remix'})
        CollapseRepeatedValuesRule().apply(song)
        self.assertEqual(
            song.tag_collection.get_item_as_array(ORIGINAL_TITLE), ['Angerfist - Raise Your Fist', 'Remix']
        )
        self.assertFalse(song.tag_collection.get_item(ORIGINAL_TITLE).has_changes())
        self.assertFalse(song.tag_collection.get_item(TITLE).has_changes())

    def test_other_tags_are_not_its_business(self):
        # Two identical artists are CleanTagsRule's to deduplicate, not this rule's.
        song = song_with(**{ARTIST: 'Angerfist;Angerfist'})
        CollapseRepeatedValuesRule().apply(song)
        self.assertEqual(song.tag_collection.get_item_as_array(ARTIST), ['Angerfist', 'Angerfist'])

    def test_a_song_without_the_tags_is_untouched(self):
        song = song_with()
        CollapseRepeatedValuesRule().apply(song)
        self.assertEqual(len(song.tag_collection), 0)

    def test_a_second_pass_changes_nothing(self):
        song = song_with(**{ORIGINAL_TITLE: 'B;B;A - B', TITLE: 'B;B;A'})
        rule = CollapseRepeatedValuesRule()
        rule.apply(song)
        first = {key: list(song.tag_collection.get_item_as_array(key)) for key in (ORIGINAL_TITLE, TITLE)}
        rule.apply(song)
        second = {key: list(song.tag_collection.get_item_as_array(key)) for key in (ORIGINAL_TITLE, TITLE)}
        self.assertEqual(first, second)
        self.assertEqual(first, {ORIGINAL_TITLE: ['A - B'], TITLE: ['B']})


if __name__ == '__main__':
    unittest.main()
