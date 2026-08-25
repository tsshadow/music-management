import unittest
from unittest.mock import MagicMock, patch

from services.tagger.constants import BPM
from services.tagger.Song.rules.AnalyzeBpmRule import AnalyzeBpmRule


def make_song(path='track.mp3'):
    song = MagicMock()
    song.path.return_value = path
    song.tag_collection = MagicMock()
    # A MagicMock would answer every read with a truthy mock, which the guard reads as
    # "this file already has a BPM" and skips.
    song.tag_collection.get_item_as_string.return_value = ''
    return song


class OneElementArray:
    """Stands in for what librosa 0.10.1+ returns from beat_track.

    Not a real ndarray: services/tests/mock_base.py replaces numpy with a MagicMock for
    the whole session, and a MagicMock converts to 1.0, which would let a broken
    conversion pass. This reproduces the two properties that matter -- item() yields the
    value, and round() refuses.
    """

    def __init__(self, value):
        self._value = value

    def item(self):
        return self._value

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


    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.load')
    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.beat.beat_track')
    def test_a_tempo_returned_as_an_array_is_still_stored(self, mock_beat_track, mock_load):
        mock_load.return_value = ('dummy_audio', 44100)
        mock_beat_track.return_value = (OneElementArray(153.6), None)
        song = make_song()
        AnalyzeBpmRule().apply(song)
        song.tag_collection.set_item.assert_called_once_with(BPM, '154')

    def test_the_old_code_path_would_have_thrown_on_that_array(self):
        # Guards the reason the conversion exists: round() on the array raises
        # TypeError, and apply swallows that, so the rule silently stored no BPM.
        with self.assertRaises(TypeError):
            round(OneElementArray(153.6))

    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.load')
    def test_a_song_that_already_has_a_bpm_is_not_decoded_again(self, mock_load):
        song = make_song()
        song.tag_collection.get_item_as_string.return_value = '150'
        AnalyzeBpmRule().apply(song)
        mock_load.assert_not_called()
        song.tag_collection.set_item.assert_not_called()

    @patch('services.tagger.Song.rules.AnalyzeBpmRule.librosa.load')
    def test_a_blank_bpm_tag_does_not_count_as_a_bpm(self, mock_load):
        mock_load.side_effect = RuntimeError('stop here')
        song = make_song()
        song.tag_collection.get_item_as_string.return_value = '   '
        AnalyzeBpmRule().apply(song)
        mock_load.assert_called_once()


if __name__ == '__main__':
    unittest.main()
