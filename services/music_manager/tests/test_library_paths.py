"""Every spelling of one file path, in one place.

LMS and muma mount the same music tree at different roots, so a lookup that
knows only one of them silently matches nothing.
"""
import unittest

from services.music_manager.library_paths import candidate_paths


class CandidatePathsTest(unittest.TestCase):

    def test_the_given_path_comes_first(self):
        result = candidate_paths('/mnt/music/Angerfist/Raise.mp3')
        self.assertEqual(result[0], '/mnt/music/Angerfist/Raise.mp3')

    def test_an_lms_path_yields_the_muma_spelling(self):
        result = candidate_paths('/music/Angerfist/Raise.mp3')
        self.assertIn('/mnt/music/Angerfist/Raise.mp3', result)

    def test_a_muma_path_yields_the_lms_spelling(self):
        result = candidate_paths('/mnt/music/Angerfist/Raise.mp3')
        self.assertIn('/music/Angerfist/Raise.mp3', result)

    def test_the_relative_spelling_is_offered_too(self):
        result = candidate_paths('/mnt/music/Angerfist/Raise.mp3')
        self.assertIn('Angerfist/Raise.mp3', result)

    def test_there_are_no_duplicates(self):
        result = candidate_paths('/mnt/music/Angerfist/Raise.mp3')
        self.assertEqual(len(result), len(set(result)))

    def test_a_path_under_neither_root_is_left_alone(self):
        result = candidate_paths('/elsewhere/Raise.mp3')
        self.assertEqual(result[0], '/elsewhere/Raise.mp3')
