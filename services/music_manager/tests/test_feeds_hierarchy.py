import unittest

from services.music_manager.feeds.hierarchy import ancestors, deepest

PARENTS = {'uptempo': {'hardcore'}, 'upterror': {'uptempo', 'terror'}, 'terror': {'hardcore'}}


class HierarchyTest(unittest.TestCase):
    def test_ancestors_walks_every_parent(self):
        self.assertEqual(ancestors('upterror', PARENTS), {'uptempo', 'terror', 'hardcore'})

    def test_a_genre_without_parents_has_no_ancestors(self):
        self.assertEqual(ancestors('hardcore', PARENTS), set())

    def test_deepest_drops_a_parent_its_own_child_already_covers(self):
        self.assertEqual(deepest({'uptempo', 'hardcore'}, PARENTS), {'uptempo'})

    def test_a_lone_parent_is_the_deepest_information_there_is(self):
        self.assertEqual(deepest({'hardcore'}, PARENTS), {'hardcore'})

    def test_unrelated_genres_both_survive(self):
        self.assertEqual(deepest({'uptempo', 'frenchcore'}, PARENTS), {'uptempo', 'frenchcore'})

    def test_a_cycle_terminates(self):
        cyclic = {'a': {'b'}, 'b': {'a'}}
        self.assertEqual(ancestors('a', cyclic), {'a', 'b'})
