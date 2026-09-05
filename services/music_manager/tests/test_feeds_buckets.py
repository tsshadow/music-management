import unittest

from services.music_manager.feeds.buckets import bucket_of, dominant_genre
from services.music_manager.feeds.profile import TAIL

SHARES = {'uptempo': 0.6, 'raw': 0.4, TAIL: 0.0}
LABEL_GENRE = {'peacock records': 'uptempo'}
ARTIST_GENRE = {'angerfist': 'raw'}
PARENTS = {'uptempo': {'hardcore'}}


class DominantGenreTest(unittest.TestCase):
    def test_a_label_that_only_releases_one_style_has_a_dominant_genre(self):
        self.assertEqual(dominant_genre({'uptempo': 90, 'raw': 10}), 'uptempo')

    def test_a_split_catalogue_has_none(self):
        self.assertIsNone(dominant_genre({'uptempo': 50, 'hardcore': 50}))

    def test_no_tagged_tracks_at_all_has_none(self):
        self.assertIsNone(dominant_genre({}))

    def test_when_counts_tie_alphabetically_first_wins(self):
        self.assertEqual(dominant_genre({'raw': 50, 'uptempo': 50}, min_share=0.5), 'raw')

    def test_a_majority_below_min_share_has_none(self):
        self.assertIsNone(dominant_genre({'uptempo': 50, 'raw': 50}, min_share=0.6))


class BucketOfTest(unittest.TestCase):
    def test_its_own_genre_wins(self):
        candidate = {'genres': ['Uptempo'], 'label': 'Peacock Records', 'artist': 'Angerfist'}
        self.assertEqual(bucket_of(candidate, SHARES, LABEL_GENRE, ARTIST_GENRE, PARENTS), ('uptempo', 'genre'))

    def test_an_untagged_release_borrows_its_label_s_genre(self):
        candidate = {'genres': [], 'label': 'Peacock Records', 'artist': 'Unknown'}
        self.assertEqual(
            bucket_of(candidate, SHARES, LABEL_GENRE, ARTIST_GENRE, PARENTS), ('uptempo', 'label:peacock records')
        )

    def test_without_a_label_it_borrows_its_artist_s_genre(self):
        candidate = {'genres': [], 'label': None, 'artist': 'Angerfist'}
        self.assertEqual(bucket_of(candidate, SHARES, LABEL_GENRE, ARTIST_GENRE, PARENTS), ('raw', 'artist:angerfist'))

    def test_a_rip_with_nothing_known_competes_for_the_leftovers(self):
        candidate = {'genres': [], 'label': None, 'artist': 'Nobody'}
        self.assertEqual(bucket_of(candidate, SHARES, LABEL_GENRE, ARTIST_GENRE, PARENTS), (TAIL, 'tail'))

    def test_a_genre_nobody_has_a_share_for_falls_through_to_the_label(self):
        candidate = {'genres': ['Frenchcore'], 'label': 'Peacock Records', 'artist': 'Nobody'}
        self.assertEqual(
            bucket_of(candidate, SHARES, LABEL_GENRE, ARTIST_GENRE, PARENTS), ('uptempo', 'label:peacock records')
        )

    def test_the_deepest_of_its_own_genres_is_the_one_that_counts(self):
        candidate = {'genres': ['Uptempo', 'Hardcore'], 'label': None, 'artist': None}
        self.assertEqual(bucket_of(candidate, SHARES, LABEL_GENRE, ARTIST_GENRE, PARENTS), ('uptempo', 'genre'))

    def test_two_unrelated_deepest_genres_both_with_shares_picks_alphabetically_first(self):
        unrelated_parents = {'raw': set(), 'uptempo': set()}
        candidate = {'genres': ['Raw', 'Uptempo'], 'label': None, 'artist': None}
        self.assertEqual(bucket_of(candidate, SHARES, LABEL_GENRE, ARTIST_GENRE, unrelated_parents), ('raw', 'genre'))

    def test_a_fully_bare_candidate_with_no_metadata_lands_in_tail(self):
        candidate = {'genres': [], 'label': None, 'artist': None}
        self.assertEqual(bucket_of(candidate, SHARES, LABEL_GENRE, ARTIST_GENRE, PARENTS), (TAIL, 'tail'))
