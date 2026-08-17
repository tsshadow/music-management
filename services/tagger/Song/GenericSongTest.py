import unittest
from unittest.mock import MagicMock, patch

from services.tagger.constants import COPYRIGHT
from services.tagger.Song.GenericSong import GenericSong


def song_with(**accessors):
    """A GenericSong with no file behind it, whose tag accessors return fixed values."""
    song = GenericSong.__new__(GenericSong)
    song.rules = []
    song.tag_collection = MagicMock()
    for name, value in accessors.items():
        setattr(song, name, lambda value=value: value)
    return song


class CalculateCopyrightTest(unittest.TestCase):

    def test_the_album_artist_and_release_year_form_the_copyright(self):
        song = song_with(album_artist='Masters of Hardcore', date='2024-03-01')

        self.assertEqual(song.calculate_copyright(), 'Masters of Hardcore (2024)')

    def test_a_bare_year_is_used_as_is(self):
        song = song_with(album_artist='Masters of Hardcore', date='2024')

        self.assertEqual(song.calculate_copyright(), 'Masters of Hardcore (2024)')

    def test_without_a_date_the_publisher_stands_in(self):
        song = song_with(album_artist='Masters of Hardcore', date='', publisher='Roughstate')

        self.assertEqual(song.calculate_copyright(), 'Roughstate')

    def test_without_an_album_artist_there_is_nothing_to_derive(self):
        song = song_with(album_artist='', date='2024')

        self.assertIsNone(song.calculate_copyright())


class GenericSongParseTest(unittest.TestCase):

    def parse(self, song):
        with patch('services.tagger.Song.GenericSong.BaseSong.parse') as base_parse:
            song.parse()
        return base_parse

    def test_a_missing_copyright_is_filled_in(self):
        song = song_with(copyright='', album_artist='Masters of Hardcore', date='2024')
        song.sort_genres = MagicMock()

        self.parse(song)

        song.tag_collection.set_item.assert_called_once_with(COPYRIGHT, 'Masters of Hardcore (2024)')

    def test_an_existing_copyright_is_left_alone(self):
        song = song_with(copyright='Roughstate', album_artist='Masters of Hardcore', date='2024')
        song.sort_genres = MagicMock()

        self.parse(song)

        song.tag_collection.set_item.assert_not_called()

    def test_nothing_is_written_when_no_copyright_can_be_derived(self):
        song = song_with(copyright='', album_artist='', date='')
        song.sort_genres = MagicMock()

        self.parse(song)

        song.tag_collection.set_item.assert_not_called()

    def test_the_genres_are_sorted_before_the_rules_run(self):
        song = song_with(copyright='Roughstate')
        song.sort_genres = MagicMock()

        self.parse(song)

        song.sort_genres.assert_called_once()

    def test_the_full_rule_chain_is_queued_and_handed_to_the_base_song(self):
        song = song_with(copyright='Roughstate')
        song.sort_genres = MagicMock()

        base_parse = self.parse(song)

        self.assertEqual(
            [type(rule).__name__ for rule in song.rules],
            [
                'InferRemixerFromTitleRule',
                'InferFestivalFromTitleRule',
                'InferPodcastFromTitleRule',
                'CleanTagsRule',
                'InferGenreFromArtistRule',
                'InferGenreFromSubgenreRule',
                'CleanTagsRule',
                'AddMissingArtistToDatabaseRule',
                'ResolveGenreRule',
                'CheckArtistRule',
                'ReplaceInvalidUnicodeRule',
            ],
        )
        base_parse.assert_called_once()


class GenericSongLoadingTest(unittest.TestCase):

    def test_a_freshly_loaded_song_has_no_catalog_number_yet(self):
        with patch('services.tagger.Song.GenericSong.BaseSong.__init__', return_value=None) as base_init:
            song = GenericSong('/music/test.mp3')

        base_init.assert_called_once_with('/music/test.mp3')
        self.assertIsNone(song._catalog_number)


if __name__ == '__main__':
    unittest.main()
