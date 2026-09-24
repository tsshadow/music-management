import unittest
from unittest.mock import MagicMock, patch

from services.tagger.constants import ARTIST
from services.tagger.Song.rules.AddMissingArtistToDatabaseRule import AddMissingArtistToDatabaseRule
from services.tagger.Song.TagCollection import TagCollection


class RealTagSong:
    """A song backed by a real TagCollection, so the test sees what the rule did to the tag."""

    def __init__(self, artists: str):
        self.tag_collection = TagCollection(None)
        self.tag_collection.add(ARTIST, artists)

    def library_artists(self):
        """The live artist list, as BaseSong.library_artists returns it."""
        return self.tag_collection.get_item_as_array(ARTIST)

    def title(self):
        """A fixed title for the prompt."""
        return 'Some Title'

    def path(self):
        """A fixed path for the prompt."""
        return '/some/path/file.mp3'


class AddMissingArtistToDatabaseRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.library_artists.return_value = ['Wrong Artist']
        self.song.path.return_value = '/some/path/file.mp3'
        self.song.title.return_value = 'Some Title'
        self.song.tag_collection.get_item.return_value = MagicMock()
        self.artist_table = MagicMock()
        self.ignored_table = MagicMock()

    def test_does_nothing_if_artist_exists(self):
        rule = AddMissingArtistToDatabaseRule(self.artist_table, self.ignored_table)
        self.artist_table.exists.return_value = True
        self.ignored_table.exists.return_value = False
        rule.apply(self.song)
        self.artist_table.add.assert_not_called()
        self.ignored_table.add.assert_not_called()

    def test_removes_artist_if_in_ignored_table_without_correction(self):
        rule = AddMissingArtistToDatabaseRule(self.artist_table, self.ignored_table)
        self.artist_table.exists.return_value = False
        self.ignored_table.exists.return_value = True
        self.ignored_table.get_corrected.return_value = None
        tag = self.song.tag_collection.get_item.return_value
        rule.apply(self.song)
        tag.remove.assert_called_once_with('Wrong Artist')
        self.ignored_table.add.assert_not_called()

    def test_replaces_artist_if_in_ignored_table_with_correction(self):
        song = RealTagSong('Wrong Artist;Known Artist')
        self.artist_table.exists.side_effect = lambda x: x == 'Known Artist'
        self.ignored_table.exists.side_effect = lambda x: x == 'Wrong Artist'
        self.ignored_table.get_corrected.return_value = 'Corrected Artist'
        AddMissingArtistToDatabaseRule(self.artist_table, self.ignored_table).apply(song)
        # In place: appending the correction made it the second artist, not the first.
        self.assertEqual(song.library_artists(), ['Corrected Artist', 'Known Artist'])
        self.ignored_table.add.assert_not_called()

    def test_ignored_artist_is_really_removed_from_the_artist_tag(self):
        # The removal used get_item('ARTIST'), a tag nobody reads -- the constant is
        # 'artist' -- so the ignored name stayed on the file.
        song = RealTagSong('Wrong Artist;Known Artist;Other Wrong')
        self.artist_table.exists.side_effect = lambda x: x == 'Known Artist'
        self.ignored_table.exists.return_value = True
        self.ignored_table.get_corrected.return_value = None
        AddMissingArtistToDatabaseRule(self.artist_table, self.ignored_table).apply(song)
        self.assertEqual(song.library_artists(), ['Known Artist'])
        self.assertNotIn('ARTIST', song.tag_collection.get())

    @patch.object(AddMissingArtistToDatabaseRule, 'get_user_input', return_value='j')
    def test_adds_artist_when_user_confirms(self, _):
        rule = AddMissingArtistToDatabaseRule(self.artist_table, self.ignored_table, ask_for_missing=True)
        self.artist_table.exists.return_value = False
        self.ignored_table.exists.return_value = False
        rule.apply(self.song)
        self.artist_table.add.assert_called_once_with('Wrong Artist')
        self.ignored_table.add.assert_not_called()

    @patch.object(AddMissingArtistToDatabaseRule, 'get_user_input', return_value='n')
    def test_adds_to_ignored_when_user_rejects(self, _):
        rule = AddMissingArtistToDatabaseRule(self.artist_table, self.ignored_table, ask_for_missing=True)
        self.artist_table.exists.return_value = False
        self.ignored_table.exists.return_value = False
        rule.apply(self.song)
        self.artist_table.add.assert_not_called()
        self.ignored_table.add.assert_called_once_with('Wrong Artist')
        self.song.tag_collection.get_item.return_value.remove.assert_called_once_with('Wrong Artist')

    @patch.object(AddMissingArtistToDatabaseRule, 'get_user_input', return_value='Real Artist')
    def test_adds_corrected_artist(self, _):
        song = RealTagSong('Wrong Artist;Known Artist')
        self.artist_table.exists.side_effect = lambda x: x == 'Known Artist'
        self.ignored_table.exists.return_value = False
        AddMissingArtistToDatabaseRule(self.artist_table, self.ignored_table, ask_for_missing=True).apply(song)
        self.artist_table.add.assert_not_called()
        self.ignored_table.add.assert_called_once_with('Wrong Artist', 'Real Artist')
        self.assertEqual(song.library_artists(), ['Real Artist', 'Known Artist'])

    @patch.object(AddMissingArtistToDatabaseRule, 'get_user_input', return_value='wrong artist')
    def test_adds_case_corrected_artist(self, _):
        rule = AddMissingArtistToDatabaseRule(self.artist_table, self.ignored_table, ask_for_missing=True)
        self.artist_table.exists.return_value = False
        self.ignored_table.exists.return_value = False
        rule.apply(self.song)
        self.artist_table.add.assert_called_once_with('wrong artist')
        self.ignored_table.add.assert_not_called()

    @patch.object(AddMissingArtistToDatabaseRule, 'get_user_input', return_value='')
    def test_skips_on_empty_input(self, _):
        rule = AddMissingArtistToDatabaseRule(self.artist_table, self.ignored_table, ask_for_missing=True)
        self.artist_table.exists.return_value = False
        self.ignored_table.exists.return_value = False
        rule.apply(self.song)
        self.artist_table.add.assert_not_called()
        self.ignored_table.add.assert_not_called()
        self.song.tag_collection.get_item.return_value.add.assert_not_called()
        self.song.tag_collection.get_item.return_value.remove.assert_not_called()

    def test_skips_if_artist_list_is_empty(self):
        rule = AddMissingArtistToDatabaseRule(self.artist_table, self.ignored_table)
        self.song.library_artists.return_value = []
        rule.apply(self.song)
        self.artist_table.add.assert_not_called()
        self.ignored_table.add.assert_not_called()


if __name__ == '__main__':
    unittest.main()
