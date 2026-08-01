import unittest
from unittest.mock import MagicMock
from services.common.Helpers.GenreRulesHelper import GenreRulesHelper, GenreRow, WHITE, BLACK, UNKNOWN
from services.tagger.Song.rules.ResolveGenreRule import ResolveGenreRule

ROWS = [GenreRow(1, 'Hardstyle', 'hardstyle', WHITE, None), GenreRow(2, 'Uptempo Hardcore', 'uptempo hardcore', WHITE, None), GenreRow(3, 'uptempo', 'uptempo', BLACK, 2), GenreRow(4, 'Arts', 'arts', BLACK, None)]


def song_with_genres(genres):
    tag = MagicMock()
    tag.to_array.return_value = genres
    tag_collection = MagicMock()
    tag_collection.has_item.return_value = True
    tag_collection.get_item.return_value = tag
    song = MagicMock()
    song.tag_collection = tag_collection
    song.path.return_value = 'song.mp3'
    return (song, tag)


def rule_with_recording_helper():
    helper = GenreRulesHelper(preload=False, rows=ROWS)
    helper.record_unknown = MagicMock()
    return (ResolveGenreRule(helper), helper)


class ResolveGenreRuleTest(unittest.TestCase):

    def test_keeps_whitelisted_genre_and_sorts(self):
        song, tag = song_with_genres(['Uptempo Hardcore', 'Hardstyle'])
        rule, _ = rule_with_recording_helper()
        rule.apply(song)
        tag.set.assert_called_once_with(['Hardstyle', 'Uptempo Hardcore'])

    def test_removes_blacklisted_genre(self):
        song, tag = song_with_genres(['Arts', 'Hardstyle'])
        rule, _ = rule_with_recording_helper()
        rule.apply(song)
        tag.set.assert_called_once_with(['Hardstyle'])

    def test_rewrites_genre_with_canonical_target(self):
        song, tag = song_with_genres(['uptempo'])
        rule, _ = rule_with_recording_helper()
        rule.apply(song)
        tag.set.assert_called_once_with(['Uptempo Hardcore'])

    def test_rewrite_does_not_duplicate_existing_target(self):
        song, tag = song_with_genres(['Uptempo Hardcore', 'uptempo'])
        rule, _ = rule_with_recording_helper()
        rule.apply(song)
        tag.set.assert_called_once_with(['Uptempo Hardcore'])

    def test_unknown_genre_is_recorded_but_left_in_the_tag(self):
        song, tag = song_with_genres(['Hardstyle', 'Tribecore'])
        rule, helper = rule_with_recording_helper()
        rule.apply(song)
        helper.record_unknown.assert_called_once_with('Tribecore')
        tag.set.assert_not_called()

    def test_unknown_genre_is_not_approved_on_a_second_pass(self):
        """Regression: recording an unknown genre must not make it valid.

        The rules it replaces added the genre to the backlog and then accepted it
        because it was in the backlog.
        """
        rule, helper = rule_with_recording_helper()
        first_song, _ = song_with_genres(['Tribecore'])
        rule.apply(first_song)
        second_song, second_tag = song_with_genres(['Tribecore'])
        rule.apply(second_song)
        self.assertEqual(helper.resolve('Tribecore').state, UNKNOWN)
        second_tag.set.assert_not_called()

    def test_does_nothing_without_a_genre_tag(self):
        song, tag = song_with_genres([])
        song.tag_collection.has_item.return_value = False
        rule, _ = rule_with_recording_helper()
        rule.apply(song)
        tag.set.assert_not_called()

    def test_cleans_tag_without_filtering_when_disabled(self):
        song, tag = song_with_genres(['Arts'])
        rule, helper = rule_with_recording_helper()
        rule.apply(song, filter_genres=False)
        tag.strip.assert_called_once()
        tag.set.assert_not_called()
        helper.record_unknown.assert_not_called()


if __name__ == '__main__':
    unittest.main()
