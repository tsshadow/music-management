import unittest
from unittest.mock import MagicMock, patch

from services.tagger.Song.rules.AnalyzeBpmRule import AnalyzeBpmRule
from services.tagger.constants import BPM


def make_song(path='track.mp3'):
    song = MagicMock()
    song.path.return_value = path
    song.tag_collection = MagicMock()
    return song


class AnalyzeBpmRuleTest(unittest.TestCase):

    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.load')
    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.beat.beat_track')
    def test_sets_bpm(self, mock_beat_track, mock_load):
        mock_load.return_value = ('dummy_audio', 44100)
        mock_beat_track.return_value = (153.6, None)
        song = make_song()
        AnalyzeBpmRule().apply(song)
        song.tag_collection.set_item.assert_called_once_with(BPM, '154')

    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.load')
    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.beat.beat_track')
    def test_the_tempo_is_rounded_to_a_whole_number(self, mock_beat_track, mock_load):
        mock_load.return_value = ('dummy_audio', 44100)
        mock_beat_track.return_value = (174.2, None)
        song = make_song()
        AnalyzeBpmRule().apply(song)
        song.tag_collection.set_item.assert_called_once_with(BPM, '174')

    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.load')
    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.beat.beat_track')
    def test_the_decoded_audio_and_sample_rate_are_handed_to_the_beat_tracker(self, mock_beat_track, mock_load):
        mock_load.return_value = ('dummy_audio', 48000)
        mock_beat_track.return_value = (120.0, None)
        AnalyzeBpmRule().apply(make_song('/music/some track.flac'))
        mock_load.assert_called_once_with('/music/some track.flac')
        mock_beat_track.assert_called_once_with(y='dummy_audio', sr=48000)

    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.load')
    def test_an_unreadable_file_leaves_the_tags_untouched(self, mock_load):
        mock_load.side_effect = RuntimeError('not audio')
        song = make_song()
        AnalyzeBpmRule().apply(song)  # must not raise
        song.tag_collection.set_item.assert_not_called()

    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.load')
    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.beat.beat_track')
    def test_a_beat_tracker_failure_leaves_the_tags_untouched(self, mock_beat_track, mock_load):
        mock_load.return_value = ('dummy_audio', 44100)
        mock_beat_track.side_effect = ValueError('no beats')
        song = make_song()
        AnalyzeBpmRule().apply(song)  # must not raise
        song.tag_collection.set_item.assert_not_called()


if __name__ == '__main__':
    unittest.main()
