import unittest
from unittest.mock import MagicMock

from services.tagger.constants import DATE, FESTIVAL
from services.tagger.Song.rules.InferFestivalFromTitleRule import InferFestivalFromTitleRule


class InferFestivalFromTitleRuleTest(unittest.TestCase):

    def setUp(self):
        self.song = MagicMock()
        self.song.length.return_value = 1800
        self.song.path.return_value = '/mnt/music/Youtube/Q-dance/set.m4a'
        self.song.tag_collection.get_item_as_string.return_value = 'Dr Peacock @ Defqon.1 2023'
        self.tag_collection = self.song.tag_collection
        self.festival_db = MagicMock()
        self.rule = InferFestivalFromTitleRule(helper=self.festival_db)

    def test_sets_festival_and_date(self):
        self.festival_db.get_all.return_value = [{'festival': 'Defqon.1', 'date': '2023-06-24'}]
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_any_call(FESTIVAL, 'Defqon.1')
        self.tag_collection.set_item.assert_any_call(DATE, '2023-06-24')

    def test_does_nothing_if_no_match(self):
        self.festival_db.get_all.return_value = []
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_not_called()

    def test_does_nothing_if_too_short(self):
        self.song.length.return_value = 400
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_not_called()
        self.festival_db.get_all.assert_not_called()

    def test_sets_only_festival_if_no_date(self):
        self.festival_db.get_all.return_value = [{'festival': 'Qlimax'}]
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_called_once_with(FESTIVAL, 'Qlimax')

    def test_reads_the_title_without_requiring_a_year(self):
        self.festival_db.get_all.return_value = [{'festival': 'Qlimax'}]
        self.rule.apply(self.song)
        self.festival_db.get_all.assert_called_once_with('Dr Peacock @ Defqon.1 2023')

    def test_falls_back_to_the_path_when_the_title_says_nothing(self):
        self.song.path.return_value = '/mnt/music/Livesets/Qlimax 2022/02 - Ran-D.mp3'
        self.festival_db.get_all.side_effect = [[], [{'festival': 'Qlimax'}]]
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_called_once_with(FESTIVAL, 'Qlimax')

    def test_the_path_fallback_demands_a_year(self):
        self.festival_db.get_all.side_effect = [[], []]
        self.rule.apply(self.song)
        second_call = self.festival_db.get_all.call_args_list[1]
        self.assertTrue(second_call.kwargs['require_year'])

    def test_uses_the_path_when_there_is_no_title_at_all(self):
        self.song.tag_collection.get_item_as_string.return_value = ''
        self.song.path.return_value = '/mnt/music/Livesets/Qlimax 2022/02 - Ran-D.mp3'
        self.festival_db.get_all.return_value = [{'festival': 'Qlimax'}]
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_called_once_with(FESTIVAL, 'Qlimax')

    def test_runs_when_the_length_is_unknown(self):
        self.song.length.return_value = None
        self.festival_db.get_all.return_value = [{'festival': 'Qlimax'}]
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_called_once_with(FESTIVAL, 'Qlimax')

    def test_a_set_that_names_two_events_gets_both(self):
        self.festival_db.get_all.return_value = [{'festival': 'Flashback'}, {'festival': 'Reverze'}]
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_called_once_with(FESTIVAL, 'Flashback;Reverze')

    def test_the_two_names_are_written_in_a_stable_order(self):
        self.festival_db.get_all.return_value = [{'festival': 'Reverze'}, {'festival': 'Flashback'}]
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_called_once_with(FESTIVAL, 'Flashback;Reverze')

    def test_the_same_festival_twice_is_written_once(self):
        self.festival_db.get_all.return_value = [{'festival': 'Reverze'}, {'festival': 'Reverze'}]
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_called_once_with(FESTIVAL, 'Reverze')

    def test_the_date_comes_from_the_first_match_that_knows_one(self):
        self.festival_db.get_all.return_value = [
            {'festival': 'Flashback', 'year': 2023},
            {'festival': 'Reverze', 'year': 2023, 'date': '2023-02-18'},
        ]
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_any_call(FESTIVAL, 'Flashback;Reverze')
        self.tag_collection.set_item.assert_any_call(DATE, '2023-02-18')


if __name__ == '__main__':
    unittest.main()
