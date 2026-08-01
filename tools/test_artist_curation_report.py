"""Tests for the parts of the dry-run report that make judgements.

The formatting is not tested; the seeding is, because it decides which names the
whole run treats as ground truth.
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from services.common.Helpers.ArtistNameAnalyzer import AnalyzerConfig, ArtistNameAnalyzer  # noqa: E402
from tools.artist_curation_report import analyse, build_seed, print_report  # noqa: E402


def row(name, tracks=10, sources=5):
    return {'name': name, 'tracks': tracks, 'sources': sources}


class BuildSeedTest(unittest.TestCase):

    def setUp(self):
        self.config = AnalyzerConfig()

    def test_a_clean_widespread_name_is_seeded(self):
        self.assertEqual(build_seed([row('Angerfist')], self.config), ['Angerfist'])

    def test_a_rare_name_is_not_seeded(self):
        self.assertEqual(build_seed([row('Angerfist', tracks=1)], self.config), [])

    def test_a_name_confined_to_one_folder_is_not_seeded(self):
        """Junk sprayed by one bad rule has plenty of tracks but no spread."""
        self.assertEqual(build_seed([row('Angerfist', tracks=500, sources=1)], self.config), [])

    def test_a_name_carrying_noise_is_not_seeded(self):
        self.assertEqual(build_seed([row('**FREE DOWNLOAD** DJ KURT')], self.config), [])

    def test_a_sentence_is_not_seeded(self):
        self.assertEqual(build_seed([row('Als wij samen komen(')], self.config), [])

    def test_thresholds_come_from_the_config(self):
        strict = AnalyzerConfig(bootstrap_min_tracks=100)
        self.assertEqual(build_seed([row('Angerfist', tracks=50)], strict), [])


class ReportTest(unittest.TestCase):

    def test_report_counts_every_input_row(self):
        rows = [row('Angerfist'), row('#1 Angerfist', tracks=2, sources=1)]
        analyzer = ArtistNameAnalyzer(build_seed(rows, AnalyzerConfig()))
        results = analyse(rows, analyzer)
        self.assertEqual(len(results), 2)
        out = io.StringIO()
        print_report(results, 1, len(rows), out=out)
        self.assertIn('2 names', out.getvalue())

    def test_every_row_carries_a_proposal(self):
        rows = [row('Angerfist'), row('Als wij samen komen(')]
        results = analyse(rows, ArtistNameAnalyzer([]))
        self.assertTrue(all(r['proposal'].kind for r in results))


if __name__ == '__main__':
    unittest.main()
