"""The plan the folder restructure would carry out, and when it refuses to.

The moves themselves are five directory renames, so the only thing worth pinning down is their
order and the refusal: half a restructure is far worse than none.
"""

import os
import tempfile
import unittest

from scripts.restructure_music_folders import check_moves, planned_moves


class PlannedMovesTest(unittest.TestCase):
    def test_the_two_piles_leave_before_the_tree_is_renamed(self):
        # __Free&None and __TODO live inside EPs. Rename EPs first and they travel with it.
        pairs = planned_moves('/mnt/music', revert=False)
        sources = [src for src, _dst in pairs]

        self.assertLess(sources.index('/mnt/music/EPs/__Free&None'), sources.index('/mnt/music/EPs'))
        self.assertLess(sources.index('/mnt/music/EPs/__TODO'), sources.index('/mnt/music/EPs'))

    def test_the_destinations_are_the_agreed_layout(self):
        pairs = dict(planned_moves('/mnt/music', revert=False))

        self.assertEqual(pairs['/mnt/music/EPs'], '/mnt/music/labels')
        self.assertEqual(pairs['/mnt/music/EPs/__Free&None'], '/mnt/music/songs')
        self.assertEqual(pairs['/mnt/music/EPs/__TODO'], '/mnt/music/import')
        self.assertEqual(pairs['/mnt/music/Soundcloud'], '/mnt/music/channels/soundcloud')
        self.assertEqual(pairs['/mnt/music/Youtube'], '/mnt/music/channels/youtube')

    def test_a_revert_turns_the_plan_around_in_both_senses(self):
        forward = planned_moves('/mnt/music', revert=False)
        back = planned_moves('/mnt/music', revert=True)

        self.assertEqual([(dst, src) for src, dst in forward], list(reversed(back)))

    def test_a_revert_recreates_the_tree_before_refilling_it(self):
        # labels has to be EPs again before songs and import can move back into it.
        sources = [src for src, _dst in planned_moves('/mnt/music', revert=True)]

        self.assertLess(sources.index('/mnt/music/labels'), sources.index('/mnt/music/songs'))
        self.assertLess(sources.index('/mnt/music/labels'), sources.index('/mnt/music/import'))


class CheckMovesTest(unittest.TestCase):
    def test_a_missing_source_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            problems = check_moves(planned_moves(root, revert=False))

        self.assertTrue(problems)
        self.assertTrue(any('missing source' in p for p in problems), problems)

    def test_an_occupied_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            for relative in ('EPs/__Free&None', 'EPs/__TODO', 'Soundcloud', 'Youtube'):
                os.makedirs(os.path.join(root, relative), exist_ok=True)
            # Somebody already made the destination; moving onto it would merge two trees silently.
            os.makedirs(os.path.join(root, 'labels'), exist_ok=True)

            problems = check_moves(planned_moves(root, revert=False))

        self.assertTrue(any('already exists' in p for p in problems), problems)

    def test_a_complete_layout_is_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            for relative in ('EPs/__Free&None', 'EPs/__TODO', 'Soundcloud', 'Youtube'):
                os.makedirs(os.path.join(root, relative), exist_ok=True)

            self.assertEqual(check_moves(planned_moves(root, revert=False)), [])


if __name__ == '__main__':
    unittest.main()
