import unittest
from unittest.mock import MagicMock, patch
from postprocessing.Song.rules.AddMissingArtistToDatabaseRule import AddMissingArtistToDatabaseRule


class AddMissingArtistToDatabaseRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.artists.return_value = ["Wrong Artist"]
        self.song.path.return_value = "/some/path/file.mp3"
        self.song.artist.return_value = "Wrong Artist"
        self.song.title.return_value = "Some Title"

        self.artist_table = MagicMock()
        self.ignored_table = MagicMock()

        self.rule = AddMissingArtistToDatabaseRule(artist_db=self.artist_table, ignored_db=self.ignored_table)

    def test_does_nothing_if_artist_exists(self):
        self.artist_table.exists.return_value = True
        self.ignored_table.exists.return_value = False

        self.rule.apply(self.song)

        self.artist_table.add.assert_not_called()
        self.ignored_table.add.assert_not_called()

    def test_does_nothing_if_artist_in_ignored_table(self):
        self.artist_table.exists.return_value = False
        self.ignored_table.exists.return_value = True

        self.rule.apply(self.song)

        self.artist_table.add.assert_not_called()
        self.ignored_table.add.assert_not_called()

    @patch("builtins.input", return_value="y")
    def test_adds_artist_when_user_confirms(self, mock_input):
        self.artist_table.exists.return_value = False
        self.ignored_table.exists.return_value = False

        self.rule.apply(self.song)

        self.artist_table.add.assert_called_once_with("Wrong Artist")
        self.ignored_table.add.assert_not_called()

    @patch("builtins.input", return_value="n")
    def test_adds_to_ignored_when_user_rejects(self, mock_input):
        self.artist_table.exists.return_value = False
        self.ignored_table.exists.return_value = False

        self.rule.apply(self.song)

        self.artist_table.add.assert_not_called()
        self.ignored_table.add.assert_called_once_with("Wrong Artist")

    @patch("builtins.input", return_value="Real Artist")
    def test_adds_to_ignored_with_correction(self, mock_input):
        self.artist_table.exists.return_value = False
        self.ignored_table.exists.return_value = False

        self.rule.apply(self.song)

        self.artist_table.add.assert_not_called()
        self.ignored_table.add.assert_called_once_with("Wrong Artist", "Real Artist")

    def test_skips_empty_artist_list(self):
        self.song.artists.return_value = []

        self.rule.apply(self.song)

        self.artist_table.add.assert_not_called()
        self.ignored_table.add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
