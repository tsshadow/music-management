import unittest
from unittest.mock import MagicMock
from postprocessing.Song.rules.MergeDrumAndBassGenresRule import MergeDrumAndBassGenresRule


class MergeDrumAndBassGenresRuleTest(unittest.TestCase):
    def setUp(self):
        self.rule = MergeDrumAndBassGenresRule()
        self.song = MagicMock()
        self.tag = MagicMock()
        self.song.tag_collection.has_item.return_value = True
        self.song.tag_collection.get_item.return_value = self.tag

    def _set_genres(self, genres):
        self.tag.as_list.return_value = genres

    def test_merges_drum_and_bass(self):
        self._set_genres(["drum", "bass"])
        self.rule.apply(self.song)
        self.tag.set.assert_called_once_with(["drum 'n bass"])

    def test_removes_bass_if_drum_n_bass_already_present(self):
        self._set_genres(["drum 'n bass", "bass"])
        self.rule.apply(self.song)
        self.tag.set.assert_called_once_with(["drum 'n bass"])

    def test_normalizes_dnb(self):
        self._set_genres(["dnb"])
        self.rule.apply(self.song)
        self.tag.set.assert_called_once_with(["drum 'n bass"])

    def test_normalizes_drum_and_bass(self):
        self._set_genres(["drum and bass"])
        self.rule.apply(self.song)
        self.tag.set.assert_called_once_with(["drum 'n bass"])

    def test_keeps_only_bass(self):
        self._set_genres(["bass"])
        self.rule.apply(self.song)
        self.tag.set.assert_called_once_with(["bass"])

    def test_keeps_only_drum(self):
        self._set_genres(["drum"])
        self.rule.apply(self.song)
        self.tag.set.assert_called_once_with(["drum"])

    def test_ignores_when_no_genre(self):
        self.song.tag_collection.has_item.return_value = False
        self.rule.apply(self.song)
        self.tag.set.assert_not_called()

    def test_merges_with_other_genres(self):
        self._set_genres(["drum", "bass", "hardcore"])
        self.rule.apply(self.song)
        self.tag.set.assert_called_once_with(["hardcore", "drum 'n bass"])


if __name__ == "__main__":
    unittest.main()
