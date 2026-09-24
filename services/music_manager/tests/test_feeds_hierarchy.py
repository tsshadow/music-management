import unittest

from services.music_manager.feeds.hierarchy import ancestors, deepest, find_cycles, nearest_ancestor, warn_cycles

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

    def test_a_cycle_terminates_and_a_genre_is_never_its_own_ancestor(self):
        cyclic = {'a': {'b'}, 'b': {'a'}}
        self.assertEqual(ancestors('a', cyclic), {'b'})

    def test_nearest_ancestor_prefers_the_parent_over_the_grandparent(self):
        self.assertEqual(nearest_ancestor('upterror', PARENTS, {'uptempo', 'hardcore'}), 'uptempo')

    def test_nearest_ancestor_breaks_a_same_level_tie_alphabetically(self):
        self.assertEqual(nearest_ancestor('upterror', PARENTS, {'uptempo', 'terror'}), 'terror')

    def test_nearest_ancestor_is_none_without_an_eligible_ancestor(self):
        self.assertIsNone(nearest_ancestor('uptempo', PARENTS, {'gabber'}))


CYCLIC = {'a': {'b'}, 'b': {'a'}, 'c': {'a'}, 'loop': {'loop'}}


class CyclicHierarchyTest(unittest.TestCase):
    """A cycle stored before the edit page refused one: walkers stay finite and decide the same way."""

    def test_deepest_keeps_one_member_of_a_cycle_not_none(self):
        self.assertEqual(deepest({'a', 'b'}, CYCLIC), {'a'})

    def test_deepest_choice_does_not_depend_on_iteration_order(self):
        for _ in range(20):
            self.assertEqual(deepest({'b', 'a'}, CYCLIC), {'a'})

    def test_a_genre_strictly_below_the_cycle_still_wins(self):
        self.assertEqual(deepest({'a', 'b', 'c'}, CYCLIC), {'c'})

    def test_a_self_loop_does_not_drop_the_genre(self):
        self.assertEqual(deepest({'loop'}, CYCLIC), {'loop'})

    def test_nearest_ancestor_never_returns_the_genre_itself(self):
        self.assertIsNone(nearest_ancestor('loop', CYCLIC, {'loop'}))
        self.assertEqual(nearest_ancestor('a', CYCLIC, {'a', 'b'}), 'b')

    def test_find_cycles_reports_members_sorted(self):
        self.assertEqual(find_cycles(CYCLIC), [['a', 'b'], ['loop']])

    def test_find_cycles_on_a_clean_graph_is_empty(self):
        self.assertEqual(find_cycles(PARENTS), [])

    def test_find_cycles_survives_a_long_chain(self):
        chain = {f'g{i}': {f'g{i + 1}'} for i in range(5000)}
        chain['g5000'] = {'g0'}
        self.assertEqual(len(find_cycles(chain)[0]), 5001)

    def test_warn_cycles_logs_once_at_warning(self):
        with self.assertLogs('music-manager.feeds.hierarchy', level='WARNING') as logs:
            warn_cycles(CYCLIC, 'test')
        self.assertEqual(len(logs.records), 1)
        self.assertIn('a <-> b', logs.output[0])

    def test_warn_cycles_is_silent_on_a_clean_graph(self):
        with self.assertNoLogs('music-manager.feeds.hierarchy', level='WARNING'):
            self.assertEqual(warn_cycles(PARENTS, 'test'), [])
