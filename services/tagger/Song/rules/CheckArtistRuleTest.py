import unittest
from unittest.mock import MagicMock

from services.tagger.constants import ARTIST
from services.tagger.Song.rules.CheckArtistRule import CheckArtistRule
from services.tagger.Song.TagCollection import TagCollection


class FakeSong:
    """The two things CheckArtistRule reads off a song, backed by a real TagCollection."""

    def __init__(self, artists: str):
        self.tag_collection = TagCollection(None)
        self.tag_collection.add(ARTIST, artists)
        self.tag_collection.get_item(ARTIST).clear_changes()

    def library_artists(self):
        """The live artist list, exactly as BaseSong.library_artists returns it."""
        return self.tag_collection.get_item_as_array(ARTIST)


class CasingArtistTable:
    """A library_artists stand-in that knows a few names and returns their canonical casing."""

    def __init__(self, *names):
        self.names = {name.lower(): name for name in names}

    def exists(self, name):
        """Whether the name is known, case-insensitively, as the real table matches."""
        return name.lower() in self.names

    def get(self, name):
        """The canonical spelling of a known name."""
        return self.names[name.lower()]


class CheckArtistRuleTest(unittest.TestCase):
    def setUp(self):
        self.ignored_table = MagicMock()
        self.ignored_table.get_corrected.return_value = None
        self.ignored_table.exists.return_value = False

    def rule(self, *known):
        """A rule over a casing table knowing `known`."""
        return CheckArtistRule(CasingArtistTable(*known), self.ignored_table)

    def test_canonical_casing_replaces_the_name_at_its_own_position(self):
        song = FakeSong('ANGERFIST;outsiders;Dj Mad Dog')
        self.rule('Angerfist', 'Outsiders', 'Dj Mad Dog').apply(song)
        self.assertEqual(song.library_artists(), ['Angerfist', 'Outsiders', 'Dj Mad Dog'])

    def test_a_second_pass_changes_nothing(self):
        # The loop used to mutate the list it walked: one pass turned this into
        # 'outsiders;Dj Mad Dog;Angerfist' -- a new primary artist -- and the next pass
        # reordered it again, so the file was rewritten and re-identified every retag.
        song = FakeSong('ANGERFIST;outsiders;Dj Mad Dog')
        rule = self.rule('Angerfist', 'Outsiders', 'Dj Mad Dog')
        rule.apply(song)
        first = list(song.library_artists())
        song.tag_collection.get_item(ARTIST).clear_changes()
        rule.apply(song)
        self.assertEqual(song.library_artists(), first)
        self.assertFalse(song.tag_collection.get_item(ARTIST).has_changes())

    def test_already_canonical_names_are_no_change(self):
        song = FakeSong('Angerfist;Outsiders')
        self.rule('Angerfist', 'Outsiders').apply(song)
        self.assertFalse(song.tag_collection.get_item(ARTIST).has_changes())

    def test_correction_keeps_the_position(self):
        self.ignored_table.get_corrected.side_effect = lambda x: 'Corrected Artist' if x == 'Wrong Artist' else None
        song = FakeSong('Wrong Artist;Known Artist')
        self.rule('Known Artist').apply(song)
        self.assertEqual(song.library_artists(), ['Corrected Artist', 'Known Artist'])

    def test_correction_onto_a_name_already_present_drops_the_duplicate(self):
        self.ignored_table.get_corrected.side_effect = lambda x: 'Known Artist' if x == 'Wrong Artist' else None
        song = FakeSong('Wrong Artist;Known Artist')
        self.rule('Known Artist').apply(song)
        self.assertEqual(song.library_artists(), ['Known Artist'])

    def test_ignored_artist_without_correction_is_removed_and_the_next_one_still_checked(self):
        self.ignored_table.exists.side_effect = lambda x: x == 'Wrong Artist'
        song = FakeSong('Wrong Artist;KNOWN ARTIST')
        self.rule('Known Artist').apply(song)
        self.assertEqual(song.library_artists(), ['Known Artist'])

    def test_does_nothing_if_unknown_artist(self):
        song = FakeSong('Somebody;Else')
        self.rule().apply(song)
        self.assertEqual(song.library_artists(), ['Somebody', 'Else'])
        self.assertFalse(song.tag_collection.get_item(ARTIST).has_changes())

    def test_no_artists_is_a_no_op(self):
        song = MagicMock()
        song.library_artists.return_value = []
        self.rule().apply(song)
        song.tag_collection.get_item.assert_not_called()


if __name__ == '__main__':
    unittest.main()
