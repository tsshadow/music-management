import unittest
from unittest.mock import MagicMock, patch

from services.tagger.constants import DATE, ORIGINAL_DATE
from services.tagger.Song.rules.InferReleaseDateFromNfoRule import InferReleaseDateFromNfoRule


class InferReleaseDateFromNfoRuleTest(unittest.TestCase):

    def setUp(self):
        self.song = MagicMock()
        self.song.path = MagicMock(
            return_value='/music/EPs/008 Recordings/X_-_Y-(008R017)-WEB-2026-ZzZz/01-x.mp3')
        self.tags = {}
        self.song.tag_collection.get_item_as_string = MagicMock(side_effect=lambda tag: self.tags.get(tag, ''))
        self.song.tag_collection.set_item = MagicMock()
        self.helper = MagicMock()
        self.helper.get = MagicMock(return_value=[])

    def _apply(self, nfo_text):
        rule = InferReleaseDateFromNfoRule(format_helper=self.helper)
        with patch('services.tagger.Song.rules.InferReleaseDateFromNfoRule.NfoDate.read_nfo',
                   return_value=nfo_text):
            rule.apply(self.song)

    def test_writes_the_street_date_at_day_precision(self):
        self._apply('Str.date : 16-01-2026')
        self.song.tag_collection.set_item.assert_called_once_with(ORIGINAL_DATE, '2026-01-16')

    def test_consults_the_override_table_for_the_scene_group(self):
        self.helper.get = MagicMock(return_value=['md'])
        self._apply('Releasedate : 05.06.2026')
        self.helper.get.assert_called_once_with('ZzZz')
        self.song.tag_collection.set_item.assert_called_once_with(ORIGINAL_DATE, '2026-05-06')

    def test_leaves_an_existing_day_precision_value_alone(self):
        self.tags[ORIGINAL_DATE] = '2026-01-02'
        self._apply('Str.date : 16-01-2026')
        self.song.tag_collection.set_item.assert_not_called()

    def test_upgrades_a_year_only_value(self):
        self.tags[ORIGINAL_DATE] = '2026'
        self._apply('Str.date : 16-01-2026')
        self.song.tag_collection.set_item.assert_called_once_with(ORIGINAL_DATE, '2026-01-16')

    def test_falls_back_to_a_day_precision_date_tag(self):
        self.tags[DATE] = '20260116'
        self._apply(None)
        self.song.tag_collection.set_item.assert_called_once_with(ORIGINAL_DATE, '2026-01-16')

    def test_a_year_only_date_tag_is_not_a_fallback(self):
        self.tags[DATE] = '2026'
        self._apply(None)
        self.song.tag_collection.set_item.assert_not_called()

    def test_writes_nothing_when_there_is_no_evidence(self):
        self._apply('no dates in here')
        self.song.tag_collection.set_item.assert_not_called()


if __name__ == '__main__':
    unittest.main()
