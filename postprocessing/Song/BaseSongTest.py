import unittest
from unittest.mock import patch, MagicMock, Mock

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3Tags

from postprocessing.Song.BaseSong import BaseSong, ExtensionNotSupportedException
from postprocessing.Song.Tag import Tag
from postprocessing.constants import ARTIST, GENRE, ALBUM, REMIXER, MusicFileType


class BaseSongTest(unittest.TestCase):

    @patch("postprocessing.Song.BaseSong.MP3")
    @patch("postprocessing.Song.BaseSong.EasyID3")
    def test_initialization_with_supported_extension(self, mock_easyid3, mock_mp3):
        mock_file = MagicMock()
        mock_file.tags = EasyID3()  # Mimic what TagCollection expects
        mock_mp3.return_value = mock_file

        song = BaseSong("some/path/test.mp3")
        self.assertEqual(song.extension(), ".mp3")
        self.assertEqual(song.filename(), "test.mp3")

    def test_initialization_with_unsupported_extension(self):
        with self.assertRaises(ExtensionNotSupportedException):
            BaseSong("file.unsupported")

    def test_split_artists(self):
        song = BaseSong.__new__(BaseSong)
        result = song.split_artists("Artist A & Artist B feat. Artist C")
        self.assertIn("Artist A", result)
        self.assertIn("Artist B", result)
        self.assertIn("Artist C", result)

    def test_merge_and_sort_genres(self):
        song = BaseSong.__new__(BaseSong)
        a = ["Techno", "Hardcore"]
        b = ["Hardcore", "Industrial"]
        merged = song.merge_and_sort_genres(a, b)
        self.assertEqual(merged, ["Hardcore", "Industrial", "Techno"])

    def test_sort_genres(self):
        song = BaseSong.__new__(BaseSong)
        mock_tag = MagicMock()
        mock_tag.value = ["Techno", "Hardcore", "Ambient"]
        tag_collection = MagicMock()
        tag_collection.has_item.return_value = True
        tag_collection.get_item.return_value = mock_tag

        song.tag_collection = tag_collection
        song.sort_genres()
        self.assertEqual(mock_tag.value, ["Ambient", "Hardcore", "Techno"])

    def test_tag_accessors_delegate_to_tag_collection(self):
        song = BaseSong.__new__(BaseSong)
        tag_collection = MagicMock()
        tag_collection.get_item_as_string.return_value = "test"
        tag_collection.get_item_as_array.return_value = ["test1", "test2"]
        song.tag_collection = tag_collection

        self.assertEqual(song.artist(), "test")
        self.assertEqual(song.artists(), ["test1", "test2"])
        self.assertEqual(song.genre(), "test")
        self.assertEqual(song.genres(), ["test1", "test2"])

    def test_set_tag_mp3(self):
        song = BaseSong.__new__(BaseSong)
        song.type = MusicFileType.MP3
        song.music_file = {}

        tag = Mock()
        tag.tag = ARTIST
        tag.to_string.return_value = "New Artist"

        song.set_tag(tag)
        self.assertEqual(song.music_file[ARTIST], "New Artist")

    @patch("postprocessing.Song.BaseSong.logging")
    def test_save_file_saves_only_if_changed(self, mock_logging):
        tag = Tag(tag=ARTIST, value="Original Artist")
        tag.set("Some Artist")

        song = BaseSong.__new__(BaseSong)
        song.music_file = MagicMock()
        song.path = MagicMock()
        song.set_tag = MagicMock()

        tag_collection = MagicMock()
        tag_collection.get.return_value = {ARTIST: tag}
        song.tag_collection = tag_collection

        song.save_file()

        song.music_file.save.assert_called_once()

    def test_apply_extra_info_sets_artist(self):
        song = BaseSong.__new__(BaseSong)
        tag_collection = MagicMock()
        song.tag_collection = tag_collection

        info = {"artists": ["Test Artist"]}
        song._apply_extra_info(info)
        tag_collection.set_item.assert_called_once_with(ARTIST, "Test Artist")

    @patch("postprocessing.Song.BaseSong.logging")
    def test_length_returns_none_on_error(self, mock_logging):
        song = BaseSong.__new__(BaseSong)
        song.path = lambda: "fakepath"
        song.music_file = object()  # no `info` attr
        self.assertIsNone(song.length())

    def test_remixers_accessor(self):
        song = BaseSong.__new__(BaseSong)
        tag_collection = MagicMock()
        tag_collection.get_item_as_array.return_value = ["Remixer1", "Remixer2"]
        song.tag_collection = tag_collection

        self.assertEqual(song.remixers(), ["Remixer1", "Remixer2"])


if __name__ == "__main__":
    unittest.main()
