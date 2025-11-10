import unittest
from unittest.mock import MagicMock

from postprocessing.Song.Tag import Tag
from postprocessing.constants import ARTIST, ALBUM_ARTIST, GENRE, REMIXER
from postprocessing.Song.rules.CleanTagsRule import CleanTagsRule


class CleanTagsRuleTest(unittest.TestCase):
    def setUp(self):
        self.rule = CleanTagsRule()

    def test_cleans_artist_album_artist_and_genre(self):
        tag_artist = MagicMock()
        tag_album_artist = MagicMock()
        tag_remixer = MagicMock()
        tag_genre = MagicMock()

        tag_collection = MagicMock()
        tag_collection.has_item.side_effect = lambda k: True
        tag_collection.get_item.side_effect = lambda k: {
            ARTIST: tag_artist,
            ALBUM_ARTIST: tag_album_artist,
            GENRE: tag_genre,
            REMIXER: tag_remixer,
        }[k]

        song = MagicMock()
        song.tag_collection = tag_collection

        self.rule.apply(song)

        for tag in [tag_artist, tag_album_artist, tag_genre]:
            tag.regex.assert_called_once()
            tag.strip.assert_called_once()

    def test_regex_split_on_ampersand(self):
        tag = Tag(ARTIST, ["Angerfist & Miss K8"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Angerfist", "Miss K8"]))

    def test_regex_split_on_feat(self):
        tag = Tag(ARTIST, ["Partyraiser feat. Bulletproof"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Partyraiser", "Bulletproof"]))

    def test_regex_split_on_vs(self):
        tag = Tag(ARTIST, ["Neophyte vs. Evil Activities"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Neophyte", "Evil Activities"]))

    def test_regex_split_on_plus(self):
        tag = Tag(ARTIST, ["Outsiders + The Darkraver"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Outsiders", "The Darkraver"]))

    def test_regex_split_on_x(self):
        tag = Tag(ARTIST, ["Dr. Peacock x Sefa"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Dr. Peacock", "Sefa"]))

    def test_regex_split_on_aka(self):
        tag = Tag(ARTIST, ["Radium aka Micropoint"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Radium", "Micropoint"]))

    def test_regex_split_on_and(self):
        tag = Tag(ARTIST, ["Tha Playah and Never Surrender"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Tha Playah", "Never Surrender"]))

    def test_regex_split_on_b2b(self):
        tag = Tag(ARTIST, ["Unexist b2b Drokz"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Unexist", "Drokz"]))

    def test_regex_split_on_pres(self):
        tag = Tag(ARTIST, ["Promo pres. D-Passion"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Promo", "D-Passion"]))

    def test_regex_split_on_presents(self):
        tag = Tag(ARTIST, ["Promo presents D-Passion"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Promo", "D-Passion"]))

    def test_regex_split_on_with(self):
        tag = Tag(ARTIST, ["The Sickest Squad with Detest"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["The Sickest Squad", "Detest"]))

    def test_regex_split_on_invites(self):
        tag = Tag(ARTIST, ["Fury invites Nosferatu"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Fury", "Nosferatu"]))

    def test_regex_split_on_comma(self):
        tag = Tag(ARTIST, ["Bass-D, King Matthew"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Bass-D", "King Matthew"]))

    def test_regex_split_on_chinese_comma(self):
        tag = Tag(ARTIST, ["Anime， Andy The Core"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Anime", "Andy The Core"]))

    def test_regex_split_on_colon(self):
        tag = Tag(ARTIST, ["Anime: The new world"])
        tag.regex()
        self.assertEqual(sorted(tag.value), sorted(["Anime", "The new world"]))

if __name__ == "__main__":
    unittest.main()
