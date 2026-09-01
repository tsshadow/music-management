"""The rules that decide whether two spellings are the same music.

Pure functions, no database: this is where the matching itself is pinned down,
so scrobble_rematch.py only has to be right about SQL.
"""

import unittest

from services.music_manager.scrobble_matching import (
    MatchTier,
    base_title,
    enabled_tiers,
    normalize,
    similarity,
)


class NormalizeTest(unittest.TestCase):
    def test_case_and_surrounding_space_do_not_matter(self):
        self.assertEqual(normalize('  Angerfist  '), normalize('angerfist'))

    def test_inner_whitespace_collapses(self):
        self.assertEqual(normalize('Evil   Activities'), normalize('Evil Activities'))

    def test_accents_are_folded(self):
        self.assertEqual(normalize('Sefa – Café'), normalize('Sefa - Cafe'))

    def test_punctuation_is_dropped(self):
        self.assertEqual(normalize("Don't Stop!"), normalize('Dont Stop'))

    def test_every_featuring_form_reaches_the_same_result(self):
        forms = [
            'Angerfist feat. Radical Redemption',
            'Angerfist ft. Radical Redemption',
            'Angerfist featuring Radical Redemption',
            'Angerfist & Radical Redemption',
            'Angerfist x Radical Redemption',
        ]
        results = {normalize(form) for form in forms}
        self.assertEqual(len(results), 1, results)

    def test_a_trailing_apostrophe_still_separates(self):
        self.assertEqual(normalize("Rockin' Hard"), 'rockin hard')

    def test_the_x_separator_does_not_eat_letters(self):
        self.assertEqual(normalize('Extra Bass'), 'extra bass')

    def test_empty_input_is_empty(self):
        self.assertEqual(normalize(''), '')
        self.assertEqual(normalize(None), '')


class BaseTitleTest(unittest.TestCase):
    def test_a_remix_suffix_is_removed(self):
        self.assertEqual(base_title('Raise Your Fist (Angerfist Remix)'), 'Raise Your Fist')

    def test_an_edit_suffix_is_removed(self):
        self.assertEqual(base_title('Raise Your Fist (Radio Edit)'), 'Raise Your Fist')

    def test_an_extended_suffix_is_removed(self):
        self.assertEqual(base_title('Raise Your Fist (Extended Mix)'), 'Raise Your Fist')

    def test_square_brackets_are_removed_too(self):
        self.assertEqual(base_title('Raise Your Fist [Hardcore Mix]'), 'Raise Your Fist')

    def test_a_bracket_that_is_part_of_the_name_survives(self):
        self.assertEqual(base_title('Track (Part 1)'), 'Track (Part 1)')

    def test_a_title_without_brackets_is_unchanged(self):
        self.assertEqual(base_title('Raise Your Fist'), 'Raise Your Fist')

    def test_only_the_trailing_group_is_removed(self):
        self.assertEqual(base_title('(Intro) Track (VIP Mix)'), '(Intro) Track')


class SimilarityTest(unittest.TestCase):
    def test_an_identical_pair_scores_full_marks(self):
        self.assertEqual(similarity('angerfist raise your fist', 'angerfist raise your fist'), 100)

    def test_a_single_character_typo_stays_high(self):
        score = similarity('angerfist raise your fist', 'angerfist raise your fst')
        self.assertGreaterEqual(score, 90)

    def test_two_different_tracks_score_low(self):
        score = similarity('angerfist raise your fist', 'radical redemption the summit')
        self.assertLess(score, 90)

    def test_an_empty_side_scores_nothing(self):
        self.assertEqual(similarity('', 'angerfist'), 0)


class EnabledTiersTest(unittest.TestCase):
    def test_the_default_is_the_whole_ladder(self):
        self.assertEqual(
            enabled_tiers(None),
            [MatchTier.EXACT, MatchTier.NORMALIZED, MatchTier.BASE_TITLE, MatchTier.FUZZY],
        )

    def test_a_setting_narrows_it(self):
        self.assertEqual(enabled_tiers('exact,normalized'), [MatchTier.EXACT, MatchTier.NORMALIZED])

    def test_order_follows_the_ladder_not_the_setting(self):
        self.assertEqual(enabled_tiers('fuzzy,exact'), [MatchTier.EXACT, MatchTier.FUZZY])

    def test_an_unknown_name_is_ignored_rather_than_crashing_the_worker(self):
        self.assertEqual(enabled_tiers('exact,nonsense'), [MatchTier.EXACT])

    def test_an_empty_setting_disables_everything(self):
        self.assertEqual(enabled_tiers(''), [])


if __name__ == '__main__':
    unittest.main()
