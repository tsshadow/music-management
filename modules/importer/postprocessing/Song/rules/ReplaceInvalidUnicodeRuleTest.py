import unittest
from unittest.mock import MagicMock

from postprocessing.Song.rules.ReplaceInvalidUnicodeRule import ReplaceInvalidUnicodeRule
from postprocessing.Song.Tag import Tag
from postprocessing.constants import ARTIST, ALBUM_ARTIST, GENRE


class ReplaceInvalidUnicodeRuleTest(unittest.TestCase):
    def test_replaces_invalid_unicode_chars(self):
        rule = ReplaceInvalidUnicodeRule()
        artist = Tag(ARTIST, f"Soulblast\ufeffChaotic Brotherz\ufeffMaus999")
        album_artist = Tag(ALBUM_ARTIST, f"Label\ufeffLabel2")
        genre = Tag(GENRE, f"Hardcore\ufeffUptempo")

        tag_collection = MagicMock()
        tag_collection.has_item.side_effect = lambda k: True
        tag_collection.get_item.side_effect = lambda k: {
            ARTIST: artist,
            ALBUM_ARTIST: album_artist,
            GENRE: genre,
        }[k]

        song = MagicMock()
        song.tag_collection = tag_collection

        rule.apply(song)

        self.assertEqual(artist.value, ["Soulblast", "Chaotic Brotherz", "Maus999"])
        self.assertEqual(album_artist.value, ["Label", "Label2"])
        self.assertEqual(genre.value, ["Hardcore", "Uptempo"])


if __name__ == "__main__":
    unittest.main()
