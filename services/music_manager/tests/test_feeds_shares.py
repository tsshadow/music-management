import unittest

from services.music_manager.feeds.profile import TAIL, TasteProfile, blend, genre_shares

PARENTS = {'uptempo': {'hardcore'}, 'frenchcore': {'hardcore'}, 'terror': {'hardcore'}}


class SharesTest(unittest.TestCase):
    def test_shares_sum_to_one(self):
        profile = TasteProfile(genres={'uptempo': 1.0, 'raw': 0.5, 'hardtechno': 0.2}, distinct_tracks=40)
        shares = genre_shares(profile, PARENTS)
        self.assertAlmostEqual(sum(shares.values()), 1.0)

    def test_a_small_genre_rolls_up_into_its_parent(self):
        profile = TasteProfile(genres={'hardcore': 1.0, 'frenchcore': 0.02, 'terror': 0.02}, distinct_tracks=40)
        shares = genre_shares(profile, PARENTS)
        self.assertNotIn('frenchcore', shares)
        self.assertGreater(shares['hardcore'], 0.9)

    def test_a_small_genre_with_no_eligible_parent_lands_in_the_tail(self):
        profile = TasteProfile(genres={'uptempo': 1.0, 'gabber': 0.01}, distinct_tracks=40)
        shares = genre_shares(profile, PARENTS)
        self.assertNotIn('gabber', shares)
        self.assertGreater(shares[TAIL], 0.0)

    def test_an_empty_profile_is_all_tail(self):
        shares = genre_shares(TasteProfile(), PARENTS)
        self.assertEqual(shares, {TAIL: 1.0})


class BlendTest(unittest.TestCase):
    def test_a_listener_with_no_history_gets_the_server_profile(self):
        server = TasteProfile(genres={'hardstyle': 1.0}, distinct_tracks=500, scope='user')
        blended = blend(TasteProfile(), server)
        self.assertEqual(blended.genres, {'hardstyle': 1.0})
        self.assertEqual(blended.scope, 'server')

    def test_a_thin_profile_is_mostly_the_server(self):
        user = TasteProfile(genres={'uptempo': 1.0}, distinct_tracks=6, scope='user')
        server = TasteProfile(genres={'hardstyle': 1.0}, distinct_tracks=500, scope='user')
        blended = blend(user, server)
        self.assertEqual(blended.scope, 'blended')
        self.assertLess(blended.genres['uptempo'], blended.genres['hardstyle'])

    def test_a_full_profile_is_entirely_the_listener(self):
        user = TasteProfile(genres={'uptempo': 1.0}, distinct_tracks=200, scope='user')
        server = TasteProfile(genres={'hardstyle': 1.0}, distinct_tracks=500, scope='user')
        blended = blend(user, server)
        self.assertEqual(blended.scope, 'user')
        self.assertNotIn('hardstyle', blended.genres)
