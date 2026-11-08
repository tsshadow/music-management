"""Every spelling of one file path, in one place.

LMS and muma mount the same music tree at different roots, so a lookup that
knows only one of them silently matches nothing.
"""

import os
import tempfile
import unittest
from types import SimpleNamespace

from services.music_manager.library_paths import (
    OutsideLibrary,
    candidate_paths,
    local_path,
    resolve_in_library,
    server_path,
)


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


class ServerPathTest(unittest.TestCase):
    """What muma writes into lms.db must be the file as LMS sees it (bug report 138)."""

    def test_a_muma_path_is_written_under_the_server_root(self):
        self.assertEqual(server_path('/mnt/music/artists/9/spotify-abc.jpg'), '/music/artists/9/spotify-abc.jpg')

    def test_a_server_path_is_left_alone(self):
        self.assertEqual(server_path('/music/artists/9/spotify-abc.jpg'), '/music/artists/9/spotify-abc.jpg')

    def test_a_path_under_neither_root_is_left_alone(self):
        self.assertEqual(server_path('/elsewhere/a.jpg'), '/elsewhere/a.jpg')

    def test_a_sibling_directory_sharing_the_prefix_is_not_rewritten(self):
        self.assertEqual(server_path('/mnt/music2/a.jpg'), '/mnt/music2/a.jpg')


class LocalPathTest(unittest.TestCase):
    def test_an_lms_path_gets_the_muma_spelling(self):
        self.assertEqual(local_path('/music/Angerfist/Raise.mp3'), '/mnt/music/Angerfist/Raise.mp3')

    def test_a_muma_path_and_a_foreign_path_stay(self):
        self.assertEqual(local_path('/mnt/music/Angerfist/Raise.mp3'), '/mnt/music/Angerfist/Raise.mp3')
        self.assertEqual(local_path('/srv/other.mp3'), '/srv/other.mp3')


class ResolveInLibraryTest(unittest.TestCase):
    """Only a file inside the music root, the EPs root or the import queue gets through."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = self.tmp.name
        self.music = os.path.join(base, 'music')
        self.eps = os.path.join(base, 'eps')
        self.outside = os.path.join(base, 'outside')
        for folder in (self.music, self.eps, self.outside):
            os.makedirs(folder)
        self.settings = SimpleNamespace(music_folder_path=self.music, eps_folder_path=self.eps, import_folder_path='')

    def test_a_file_in_either_root_or_the_queue_is_accepted(self):
        for path in (
            os.path.join(self.music, 'a.mp3'),
            os.path.join(self.eps, 'Scantraxx', 'b.flac'),
            os.path.join(self.eps, '__TODO', 'c.mp3'),
        ):
            with self.subTest(path=path):
                self.assertEqual(resolve_in_library(path, self.settings), os.path.realpath(path))

    def test_a_path_that_climbs_out_is_refused(self):
        with self.assertRaises(OutsideLibrary):
            resolve_in_library(os.path.join(self.music, '..', 'outside', 'a.mp3'), self.settings)

    def test_a_sibling_whose_name_starts_like_a_root_is_refused(self):
        with self.assertRaises(OutsideLibrary):
            resolve_in_library(self.music + 'x/a.mp3', self.settings)

    def test_a_symlink_out_of_the_library_is_refused(self):
        link = os.path.join(self.music, 'escape')
        os.symlink(self.outside, link)
        with self.assertRaises(OutsideLibrary):
            resolve_in_library(os.path.join(link, 'a.mp3'), self.settings)

    def test_with_no_root_configured_nothing_is_inside(self):
        empty = SimpleNamespace(music_folder_path='', eps_folder_path='', import_folder_path='')
        with self.assertRaises(OutsideLibrary):
            resolve_in_library(os.path.join(self.music, 'a.mp3'), empty)
