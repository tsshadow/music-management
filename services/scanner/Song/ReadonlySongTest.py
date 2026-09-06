import unittest
from unittest.mock import MagicMock, patch

from mutagen.flac import VCFLACDict
from mutagen.mp4 import MP4StreamInfoError

from services.scanner.Song.ReadonlySong import ReadonlySong


class ReadonlySongTest(unittest.TestCase):
    """The scanner opens every file in the library through this class.

    BaseSong's loader is not passive -- it deletes an m4a it cannot parse and rewrites a
    FLAC whose tag keys are lower case. Inherited unchanged, merely indexing the library
    mutates it, and a mass rescan concentrates that into thousands of files at once.
    """

    def flac_file(self):
        music_file = MagicMock()
        music_file.tags = VCFLACDict()
        return music_file

    def test_an_unreadable_m4a_is_reported_but_not_deleted(self):
        with (
            patch('services.tagger.Song.BaseSong.MP4', side_effect=MP4StreamInfoError('broken')),
            patch('services.tagger.Song.BaseSong.os.remove') as remove,
            patch('services.tagger.Song.BaseSong.log_broken_file') as log_broken,
        ):
            song = ReadonlySong('some/path/test.m4a')

        remove.assert_not_called()
        log_broken.assert_called_once_with('some/path/test.m4a')
        self.assertFalse(hasattr(song, 'tag_collection'))

    def test_a_flac_is_not_normalized_on_load(self):
        with (
            patch('services.tagger.Song.BaseSong.FLAC', return_value=self.flac_file()),
            patch('services.tagger.Song.BaseSong.NormalizeFlacTagsRule') as normalize,
        ):
            ReadonlySong('some/path/test.flac')

        normalize.return_value.apply.assert_not_called()

    def test_a_flac_with_lowercase_keys_is_not_saved(self):
        """The rule is what saved it, so the real rule has to run for this to mean anything."""
        music_file = self.flac_file()
        music_file.tags['artist'] = ['Angerfist']
        with patch('services.tagger.Song.BaseSong.FLAC', return_value=music_file):
            ReadonlySong('some/path/test.flac')

        music_file.save.assert_not_called()

    def test_a_flac_with_lowercase_keys_is_still_read_case_insensitively(self):
        """Skipping the normalization must not cost the scanner the tags themselves."""
        music_file = self.flac_file()
        music_file.tags['artist'] = ['Angerfist']
        with patch('services.tagger.Song.BaseSong.FLAC', return_value=music_file):
            song = ReadonlySong('some/path/test.flac')

        self.assertEqual(song.artist(), 'Angerfist')

    def test_no_rules_run_on_a_readonly_song(self):
        with patch('services.tagger.Song.BaseSong.FLAC', return_value=self.flac_file()):
            song = ReadonlySong('some/path/test.flac')

        self.assertEqual(song.rules, [])


if __name__ == '__main__':
    unittest.main()
