import unittest

from services.music_manager.feeds.quota import allocate, redistribute

SHARES = {'uptempo': 0.50, 'raw': 0.25, 'hardtechno': 0.10, '__tail__': 0.15}


class AllocateTest(unittest.TestCase):
    def test_the_places_are_divided_by_share(self):
        self.assertEqual(allocate(SHARES, 30), {'uptempo': 15, 'raw': 8, 'hardtechno': 3, '__tail__': 4})

    def test_every_place_is_handed_out(self):
        self.assertEqual(sum(allocate(SHARES, 30).values()), 30)
        self.assertEqual(sum(allocate(SHARES, 7).values()), 7)

    def test_a_small_share_still_gets_a_place_when_there_is_room(self):
        # 10% of 30 is 3 places; rounding it away is exactly the failure this
        # feature exists to prevent.
        self.assertGreaterEqual(allocate(SHARES, 30)['hardtechno'], 1)

    def test_no_shares_means_no_places(self):
        self.assertEqual(allocate({}, 30), {})


class RedistributeTest(unittest.TestCase):
    def test_a_share_nobody_released_gives_its_places_away(self):
        allocation = {'uptempo': 15, 'raw': 8, 'hardtechno': 3, '__tail__': 4}
        available = {'uptempo': 40, 'raw': 0, 'hardtechno': 9, '__tail__': 20}
        result = redistribute(allocation, available)
        self.assertEqual(result['raw'], 0)
        self.assertEqual(sum(result.values()), 30)

    def test_nothing_is_allocated_beyond_what_exists(self):
        allocation = {'uptempo': 15, 'raw': 15}
        available = {'uptempo': 2, 'raw': 2}
        result = redistribute(allocation, available)
        self.assertEqual(result, {'uptempo': 2, 'raw': 2})

    def test_a_full_house_is_left_alone(self):
        allocation = {'uptempo': 15, 'raw': 15}
        available = {'uptempo': 50, 'raw': 50}
        self.assertEqual(redistribute(allocation, available), allocation)
