import unittest
from unittest.mock import MagicMock
from postprocessing.Song.rules.InferFestivalFromTitleRule import InferFestivalFromTitleRule
from postprocessing.constants import TITLE, FESTIVAL, DATE


class InferFestivalFromTitleRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.length.return_value = 1800
        self.song.tag_collection.get_item_as_string.return_value = "Dr Peacock @ Defqon.1 2023"
        self.tag_collection = self.song.tag_collection

        self.festival_db = MagicMock()
        self.rule = InferFestivalFromTitleRule(helper=self.festival_db)

    def test_sets_festival_and_date(self):
        self.festival_db.get.return_value = {
            "festival": "Defqon.1",
            "date": "2023-06-24"
        }

        self.rule.apply(self.song)

        self.tag_collection.set_item.assert_any_call(FESTIVAL, "Defqon.1")
        self.tag_collection.set_item.assert_any_call(DATE, "2023-06-24")

    def test_does_nothing_if_no_match(self):
        self.festival_db.get.return_value = None
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_not_called()

    def test_does_nothing_if_too_short(self):
        self.song.length.return_value = 400
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_not_called()

    def test_sets_only_festival_if_no_date(self):
        self.festival_db.get.return_value = {"festival": "Qlimax"}
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_called_once_with(FESTIVAL, "Qlimax")

    def test_skips_if_no_title(self):
        self.song.tag_collection.get_item_as_string.return_value = ""
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_not_called()


if __name__ == "__main__":
    unittest.main()
