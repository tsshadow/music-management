"""The whole genre path over a real TagCollection: read, clean, resolve.

The rule tests on either side mock the tag, which is how 'Drum & Bass' could be
split into 'Drum' and 'Bass' by the artist splitter for as long as it was: every
test saw only the call, never what it did to the value.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from mutagen.easyid3 import EasyID3

from services.common.Helpers.GenreRulesHelper import BLACK, WHITE, GenreRow, GenreRulesHelper
from services.tagger.constants import GENRE
from services.tagger.Song.rules.CleanTagsRule import CleanTagsRule
from services.tagger.Song.rules.ResolveGenreRule import ResolveGenreRule
from services.tagger.Song.TagCollection import TagCollection

ROWS = [
    GenreRow(1, 'Drum & Bass', GenreRulesHelper.normalize('Drum & Bass'), WHITE, None),
    GenreRow(2, 'Hardcore', GenreRulesHelper.normalize('Hardcore'), WHITE, None),
    GenreRow(3, 'Uptempo', GenreRulesHelper.normalize('Uptempo'), WHITE, None),
    GenreRow(4, 'Film & Animation', GenreRulesHelper.normalize('Film & Animation'), BLACK, None),
    GenreRow(5, 'Hardcore: Uptempo', GenreRulesHelper.normalize('Hardcore: Uptempo'), WHITE, None),
]


def song_with_genre(value):
    """A song whose tags come off an mp3 tag dict, the way TagCollection reads a file."""
    tags = EasyID3()
    tags['genre'] = value if isinstance(value, list) else [value]
    collection = TagCollection(tags)
    return SimpleNamespace(tag_collection=collection, path=lambda: 'song.mp3')


def run_genre_path(song):
    """CleanTagsRule twice around the inference rules and then ResolveGenreRule, as GenericSong wires them."""
    helper = GenreRulesHelper(preload=False, rows=ROWS, expansions={})
    helper.record_unknown = MagicMock()
    CleanTagsRule().apply(song)
    CleanTagsRule().apply(song)
    ResolveGenreRule(helper).apply(song)
    return helper


class GenrePathTest(unittest.TestCase):
    def test_drum_and_bass_survives_and_resolves_against_its_curated_row(self):
        song = song_with_genre('Drum & Bass')
        helper = run_genre_path(song)
        self.assertEqual(song.tag_collection.get_item_as_array(GENRE), ['Drum & Bass'])
        helper.record_unknown.assert_not_called()

    def test_a_colon_in_a_curated_genre_is_kept(self):
        song = song_with_genre('Hardcore: Uptempo')
        run_genre_path(song)
        self.assertEqual(song.tag_collection.get_item_as_array(GENRE), ['Hardcore: Uptempo'])

    def test_a_blacklisted_youtube_category_with_an_ampersand_is_removed(self):
        # Split into 'Film' and 'Animation', the seeded blacklist row never matched and
        # both halves went to the curation queue instead.
        song = song_with_genre(['Film & Animation', 'Hardcore'])
        helper = run_genre_path(song)
        self.assertEqual(song.tag_collection.get_item_as_array(GENRE), ['Hardcore'])
        helper.record_unknown.assert_not_called()

    def test_semicolon_and_slash_still_separate_genres(self):
        song = song_with_genre('Hardcore;Drum & Bass')
        run_genre_path(song)
        self.assertEqual(song.tag_collection.get_item_as_array(GENRE), ['Drum & Bass', 'Hardcore'])

        song = song_with_genre('Hardcore/Uptempo')
        run_genre_path(song)
        self.assertEqual(song.tag_collection.get_item_as_array(GENRE), ['Hardcore', 'Uptempo'])

    def test_an_unknown_genre_with_an_ampersand_is_queued_whole(self):
        song = song_with_genre('Bass & Beats')
        helper = run_genre_path(song)
        helper.record_unknown.assert_called_once_with('Bass & Beats')
        self.assertEqual(song.tag_collection.get_item_as_array(GENRE), ['Bass & Beats'])

    def test_a_second_pass_changes_nothing(self):
        song = song_with_genre(['Drum & Bass', 'Hardcore'])
        run_genre_path(song)
        song.tag_collection.get_item(GENRE).clear_changes()
        run_genre_path(song)
        self.assertFalse(song.tag_collection.get_item(GENRE).has_changes())
