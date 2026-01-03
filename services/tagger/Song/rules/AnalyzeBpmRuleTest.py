import unittest
from unittest.mock import MagicMock, patch
from services.tagger.Song.rules.AnalyzeBpmRule import AnalyzeBpmRule
from services.tagger.constants import BPM

class AnalyzeBpmRuleTest(unittest.TestCase):

    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.load')
    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.beat.beat_track')
    def test_sets_bpm(self, mock_beat_track, mock_load):
        mock_load.return_value = ('dummy_audio', 44100)
        mock_beat_track.return_value = (153.6, None)
        song = MagicMock()
        song.path.return_value = 'track.mp3'
        song.tag_collection = MagicMock()
        rule = AnalyzeBpmRule()
        rule.apply(song)
        song.tag_collection.set_item.assert_called_once_with(BPM, '154')
if __name__ == '__main__':
    unittest.main()