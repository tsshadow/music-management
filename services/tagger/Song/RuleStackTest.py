"""rule_stack: the rules of a song type, shared by every file of a round and fresh outside one."""

import time
import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers import RoundScope
from services.common.Helpers.TableHelper import TableHelper
from services.tagger.constants import ARTIST, ORIGINAL_TITLE, TITLE
from services.tagger.Song import rule_stack
from services.tagger.Song.GenericSong import GenericSong
from services.tagger.Song.rules.InferArtistFromTitleRule import InferArtistFromTitleRule


def bare_generic_song():
    """A GenericSong with no file behind it, as GenericSongTest builds one."""
    song = GenericSong.__new__(GenericSong)
    song.rules = []
    song.tag_collection = MagicMock()
    song.copyright = lambda: 'Roughstate'
    song.sort_genres = MagicMock()
    return song


def parse(song):
    with patch('services.tagger.Song.GenericSong.BaseSong.parse'):
        song.parse()


class RulesForTest(unittest.TestCase):
    def test_outside_a_round_every_call_builds_new_rules(self):
        first = rule_stack.rules_for(rule_stack.SOUNDCLOUD)
        second = rule_stack.rules_for(rule_stack.SOUNDCLOUD)
        self.assertEqual([type(r) for r in first], [type(r) for r in second])
        self.assertTrue(all(a is not b for a, b in zip(first, second, strict=True)))

    def test_inside_a_round_the_same_rules_are_handed_out_in_a_new_list(self):
        with RoundScope.round_scope():
            first = rule_stack.rules_for(rule_stack.YOUTUBE)
            second = rule_stack.rules_for(rule_stack.YOUTUBE)
        self.assertIsNot(first, second)
        self.assertTrue(all(a is b for a, b in zip(first, second, strict=True)))

    def test_each_kind_has_its_own_rules(self):
        with RoundScope.round_scope():
            label = rule_stack.rules_for(rule_stack.LABEL)
            generic = rule_stack.rules_for(rule_stack.GENERIC)
        self.assertNotEqual([type(r).__name__ for r in label], [type(r).__name__ for r in generic])

    def test_two_songs_of_one_round_share_their_rules_and_not_their_list(self):
        first, second = bare_generic_song(), bare_generic_song()
        with RoundScope.round_scope():
            parse(first)
            parse(second)
        self.assertIsNot(first.rules, second.rules)
        self.assertTrue(all(a is b for a, b in zip(first.rules, second.rules, strict=True)))

    def test_the_youtube_stack_keeps_its_order(self):
        self.assertEqual(
            [type(rule).__name__ for rule in rule_stack.rules_for(rule_stack.YOUTUBE)],
            [
                'CleanTitleRule',
                'InferArtistFromTitleRule',
                'InferRemixerFromTitleRule',
                'InferFeatureFromTitleRule',
                'InferFestivalFromTitleRule',
                'InferPodcastFromTitleRule',
                'CleanTagsRule',
                'InferGenreFromArtistRule',
                'InferGenreFromAlbumArtistRule',
                'InferGenreFromSubgenreRule',
                'CleanTagsRule',
                'AddMissingArtistToDatabaseRule',
                'ResolveGenreRule',
                'CleanTagsRule',
                'CheckArtistRule',
                'CaptureDisplayArtistRule',
                'ReplaceInvalidUnicodeRule',
            ],
        )

    def test_the_label_stack_keeps_its_order(self):
        self.assertEqual(
            [type(rule).__name__ for rule in rule_stack.rules_for(rule_stack.LABEL)],
            [
                'InferRemixerFromTitleRule',
                'CleanTagsRule',
                'InferGenreFromArtistRule',
                'InferGenreFromLabelRule',
                'InferGenreFromSubgenreRule',
                'CleanTagsRule',
                'AddMissingArtistToDatabaseRule',
                'ResolveGenreRule',
                'CleanTagsRule',
                'InferReleaseDateFromNfoRule',
                'CheckArtistRule',
                'ReplaceInvalidUnicodeRule',
            ],
        )


def cached_artist_table(names):
    """A real, caching TableHelper holding `names`, without a database behind it."""
    table = TableHelper('library_artists', 'name', preload=False)
    table.cache_enabled = True
    table._loaded_at = time.monotonic()
    table._publish(frozenset(names), {name.lower(): name for name in names})
    return table


class RoundLongArtistRuleTest(unittest.TestCase):
    """The rule outlives a file now, so it must follow library_artists' snapshot as a per-file rule did."""

    def setUp(self):
        self.ignored = MagicMock(**{'get_all.return_value': []})
        self.genres = MagicMock(**{'get_all.return_value': []})

    def apply(self, rule, title):
        song = MagicMock()
        song.path = lambda: '/music/Soundcloud/uploader/track.mp3'
        song.tag_collection.has_item.return_value = True
        song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: '',
            TITLE: title,
            ORIGINAL_TITLE: title,
        }[key]
        rule.apply(song)
        return song

    def test_an_artist_published_mid_round_is_recognised_by_the_next_file(self):
        table = cached_artist_table(['Angerfist'])
        rule = InferArtistFromTitleRule(artist_db=table, ignored_db=self.ignored, genre_db=self.genres)

        # "Warm Up - Zyklon": neither side is known, so the fallback takes the left side.
        before = self.apply(rule, 'Warm Up - Zyklon')
        before.tag_collection.set_item.assert_any_call(ARTIST, 'Warm Up')

        table._publish(frozenset(['Angerfist', 'Zyklon']), {'angerfist': 'Angerfist', 'zyklon': 'Zyklon'})
        after = self.apply(rule, 'Warm Up - Zyklon')
        after.tag_collection.set_item.assert_any_call(ARTIST, 'Zyklon')
        after.tag_collection.set_item.assert_any_call(TITLE, 'Warm Up')

    def test_an_unchanged_snapshot_does_not_rebuild_the_name_sets(self):
        table = cached_artist_table(['Angerfist'])
        rule = InferArtistFromTitleRule(artist_db=table, ignored_db=self.ignored, genre_db=self.genres)
        rules = rule.rules
        self.apply(rule, 'Angerfist - Raise Your Fist')
        self.apply(rule, 'Angerfist - Raise Your Fist')
        self.assertIs(rule.rules, rules)

    def test_the_ignore_and_genre_lists_are_read_once_not_per_file(self):
        table = cached_artist_table(['Angerfist'])
        rule = InferArtistFromTitleRule(artist_db=table, ignored_db=self.ignored, genre_db=self.genres)
        for _ in range(5):
            self.apply(rule, 'Angerfist - Raise Your Fist')
        self.ignored.get_all.assert_called_once()
        self.genres.get_all.assert_called_once()


if __name__ == '__main__':
    unittest.main()
