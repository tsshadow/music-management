import unittest
from unittest.mock import MagicMock

from services.tagger.constants import MusicFileType
from services.tagger.Song.rules.NormalizeFlacTagsRule import NormalizeFlacTagsRule


def flac_song(tags):
    song = MagicMock()
    song.type = MusicFileType.FLAC
    song.music_file.tags = tags
    return song


class NormalizeFlacTagsRuleTest(unittest.TestCase):
    def setUp(self):
        self.rule = NormalizeFlacTagsRule()

    def test_lowercase_keys_are_upper_cased_and_the_file_is_written(self):
        song = flac_song({'artist': ['Angerfist'], 'Genre': ['Hardcore']})

        self.rule.apply(song)

        self.assertEqual(song.music_file.tags, {'ARTIST': ['Angerfist'], 'GENRE': ['Hardcore']})
        song.music_file.save.assert_called_once()

    def test_tags_that_are_already_upper_case_are_left_untouched(self):
        song = flac_song({'ARTIST': ['Angerfist']})

        self.rule.apply(song)

        song.music_file.save.assert_not_called()

    def test_a_file_without_tags_is_skipped(self):
        song = flac_song(None)

        self.rule.apply(song)

        song.music_file.save.assert_not_called()

    def test_a_file_without_any_tag_at_all_is_left_alone(self):
        song = flac_song({})

        self.rule.apply(song)

        song.music_file.save.assert_not_called()

    def test_other_formats_are_not_touched(self):
        song = MagicMock()
        song.type = MusicFileType.MP3

        self.rule.apply(song)

        song.music_file.save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
