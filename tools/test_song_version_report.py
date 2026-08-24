"""The dry-run summary, over rows handed in rather than fetched.

Keeping the arithmetic pure is what lets this be checked without a database; the
script around it only supplies rows.
"""
import unittest

from tools.song_version_report import summarize


def _row(track_id, artist, title, path):
    return {'id': track_id, 'artist': artist, 'title': title, 'file_path': path}


class SummarizeTest(unittest.TestCase):

    def setUp(self):
        self.rows = [
            _row(1, 'Angerfist', 'Raise Your Fist (Radio Edit)', '/m/a.mp3'),
            _row(2, 'Angerfist', 'Raise Your Fist (Extended Mix)', '/m/b.flac'),
            _row(3, 'Angerfist', 'Raise Your Fist', '/m/c.mp3'),
            _row(4, 'Angerfist', 'Raise Your Fist (Wildstylez Remix)', '/m/d.mp3'),
            _row(5, 'Angerfist', 'Stitches', '/m/e.mp3'),
        ]

    def test_it_counts_works_not_tracks(self):
        result = summarize(self.rows)
        self.assertEqual(result['tracks'], 5)
        self.assertEqual(result['works'], 3)

    def test_the_largest_group_is_reported_with_its_members(self):
        result = summarize(self.rows)
        largest = result['largest_groups'][0]
        self.assertEqual(largest['size'], 3)
        self.assertIn('Raise Your Fist (Radio Edit)', largest['titles'])

    def test_a_single_version_song_is_counted_as_such(self):
        result = summarize(self.rows)
        self.assertEqual(result['single_version_works'], 2)

    def test_the_kind_breakdown_adds_up_to_the_track_count(self):
        result = summarize(self.rows)
        self.assertEqual(sum(result['kinds'].values()), 5)

    def test_an_empty_library_does_not_divide_by_zero(self):
        result = summarize([])
        self.assertEqual(result['tracks'], 0)
        self.assertEqual(result['works'], 0)
        self.assertEqual(result['largest_groups'], [])
