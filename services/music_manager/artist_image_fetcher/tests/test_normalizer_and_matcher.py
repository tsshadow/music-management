import unittest

from services.music_manager.artist_image_fetcher.matcher import ArtistMatcher
from services.music_manager.artist_image_fetcher.normalizer import ArtistNameNormalizer


class NormalizerTest(unittest.TestCase):
    def test_an_empty_name_normalizes_to_an_empty_string(self):
        self.assertEqual(ArtistNameNormalizer.normalize(''), '')
        self.assertEqual(ArtistNameNormalizer.normalize(None), '')

    def test_separators_become_spaces_and_case_is_dropped(self):
        self.assertEqual(ArtistNameNormalizer.normalize('A-Lusion'), 'a lusion')
        self.assertEqual(ArtistNameNormalizer.normalize('Label_Records'), 'label')

    def test_repeated_whitespace_collapses(self):
        self.assertEqual(ArtistNameNormalizer.normalize('  Dj    Paul  '), 'dj paul')

    def test_trailing_marketing_suffixes_are_stripped(self):
        self.assertEqual(ArtistNameNormalizer.normalize('The Artist - Official'), 'the artist')
        self.assertEqual(ArtistNameNormalizer.normalize('Angerfist Music'), 'angerfist')
        self.assertEqual(ArtistNameNormalizer.normalize('Q-dance TV'), 'q dance')
        self.assertEqual(ArtistNameNormalizer.normalize('Hardstyle HQ'), 'hardstyle')

    def test_a_suffix_in_the_middle_of_a_name_is_kept(self):
        self.assertEqual(ArtistNameNormalizer.normalize('Official Business Crew'), 'official business crew')

    def test_sort_name_moves_a_leading_the_to_the_back(self):
        self.assertEqual(ArtistNameNormalizer.get_sort_name('The Prodigy'), 'Prodigy, The')

    def test_sort_name_leaves_other_names_alone(self):
        self.assertEqual(ArtistNameNormalizer.get_sort_name('Angerfist'), 'Angerfist')

    def test_sort_name_of_an_empty_name_is_an_empty_string(self):
        self.assertEqual(ArtistNameNormalizer.get_sort_name(''), '')
        self.assertEqual(ArtistNameNormalizer.get_sort_name(None), '')


class MatcherTest(unittest.TestCase):
    def setUp(self):
        self.matcher = ArtistMatcher()
        self.target = {'id': 1, 'name': 'A-Lusion', 'mbid': 'abc'}

    def test_an_identical_name_and_mbid_is_a_certain_match(self):
        score = self.matcher.calculate_confidence(self.target, {'name': 'A-Lusion', 'mbid': 'abc', 'source': 'spotify'})
        self.assertEqual(score, 100)

    def test_a_name_that_only_matches_after_normalization_still_scores_as_a_candidate(self):
        score = self.matcher.calculate_confidence(self.target, {'name': 'a lusion', 'source': 'lastfm'})
        self.assertGreaterEqual(score, 50)

    def test_an_unrelated_name_scores_zero(self):
        score = self.matcher.calculate_confidence(self.target, {'name': 'Different Artist', 'source': 'spotify'})
        self.assertEqual(score, 0)

    def test_a_name_that_only_matches_once_punctuation_is_dropped_scores_below_an_exact_match(self):
        exact = self.matcher.calculate_confidence(
            {'id': 1, 'name': 'Da Tweekaz'}, {'name': 'Da Tweekaz', 'source': 'lastfm'}
        )
        slug = self.matcher.calculate_confidence(
            {'id': 1, 'name': 'Da Tweekaz'}, {'name': 'DaTweekaz', 'source': 'lastfm'}
        )
        self.assertGreater(exact, slug)
        self.assertGreater(slug, 0)

    def test_a_near_miss_still_earns_partial_credit(self):
        score = self.matcher.calculate_confidence(
            {'id': 1, 'name': 'Headhunterz'}, {'name': 'Headhunterez', 'source': 'lastfm'}
        )
        self.assertGreater(score, 0)
        self.assertLess(score, 60)

    def test_a_matching_mbid_is_worth_more_than_the_name_alone(self):
        with_mbid = self.matcher.calculate_confidence(
            self.target, {'name': 'Different Artist', 'mbid': 'abc', 'source': 'lastfm'}
        )
        without = self.matcher.calculate_confidence(self.target, {'name': 'Different Artist', 'source': 'lastfm'})
        self.assertGreater(with_mbid, without)

    def test_a_mismatching_mbid_earns_no_bonus(self):
        score = self.matcher.calculate_confidence(self.target, {'name': 'A-Lusion', 'mbid': 'zzz', 'source': 'lastfm'})
        self.assertEqual(score, 60)

    def test_a_known_match_outweighs_a_name_that_does_not_look_alike(self):
        known = self.matcher.calculate_confidence(
            self.target, {'name': 'Whatever Else', 'is_known_match': True, 'source': 'spotify'}
        )
        unknown = self.matcher.calculate_confidence(self.target, {'name': 'Whatever Else', 'source': 'spotify'})
        self.assertEqual(unknown, 0)
        self.assertTrue(self.matcher.is_candidate(known))

    def test_a_label_sounding_candidate_is_penalised(self):
        plain = self.matcher.calculate_confidence(
            {'id': 1, 'name': 'Scantraxx'}, {'name': 'Scantraxx', 'source': 'lastfm'}
        )
        labelled = self.matcher.calculate_confidence(
            {'id': 1, 'name': 'Scantraxx'}, {'name': 'Scantraxx Records', 'source': 'lastfm'}
        )
        self.assertGreater(plain, labelled)

    def test_a_popular_spotify_artist_gets_a_bonus(self):
        popular = self.matcher.calculate_confidence(
            {'id': 1, 'name': 'Brennan Heart'}, {'name': 'Brennan Heart', 'source': 'spotify', 'popularity': 80}
        )
        obscure = self.matcher.calculate_confidence(
            {'id': 1, 'name': 'Brennan Heart'}, {'name': 'Brennan Heart', 'source': 'spotify', 'popularity': 5}
        )
        self.assertGreater(popular, obscure)

    def test_a_soundcloud_account_already_linked_to_this_artist_gets_a_bonus(self):
        linked = self.matcher.calculate_confidence(
            self.target, {'name': 'A-Lusion', 'source': 'soundcloud', 'linked_artist_id': 1}
        )
        unlinked = self.matcher.calculate_confidence(
            self.target, {'name': 'A-Lusion', 'source': 'soundcloud', 'linked_artist_id': 99}
        )
        self.assertGreater(linked, unlinked)

    def test_the_score_never_leaves_the_zero_to_hundred_range(self):
        huge = self.matcher.calculate_confidence(
            self.target,
            {'name': 'A-Lusion', 'mbid': 'abc', 'is_known_match': True, 'source': 'spotify', 'popularity': 99},
        )
        self.assertEqual(huge, 100)
        awful = self.matcher.calculate_confidence(self.target, {'name': 'Completely Other Records', 'source': 'lastfm'})
        self.assertEqual(awful, 0)

    def test_the_auto_accept_and_candidate_thresholds(self):
        self.assertTrue(self.matcher.should_auto_accept(80))
        self.assertFalse(self.matcher.should_auto_accept(79))
        self.assertTrue(self.matcher.is_candidate(50))
        self.assertFalse(self.matcher.is_candidate(49))


if __name__ == '__main__':
    unittest.main()
