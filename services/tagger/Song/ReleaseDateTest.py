import unittest

from services.tagger.Song.ReleaseDate import format_release_date, preferred_release_date


class PreferredReleaseDateTest(unittest.TestCase):
    def test_the_original_wins_when_it_is_at_least_as_precise(self):
        self.assertEqual(preferred_release_date('2026', '2026-09-03'), '2026-09-03')

    def test_a_bare_year_never_throws_away_a_full_date(self):
        self.assertEqual(preferred_release_date('2026-09-03', '2024'), '2026-09-03')

    def test_an_empty_original_falls_back_to_the_date(self):
        self.assertEqual(preferred_release_date('20260903', ''), '20260903')

    def test_nothing_at_all_stays_nothing(self):
        self.assertEqual(preferred_release_date('', None), '')


class FormatReleaseDateTest(unittest.TestCase):
    def test_an_iso_date_reads_as_day_month_year(self):
        self.assertEqual(format_release_date('2026-09-03'), '03-09-2026')

    def test_the_undelimited_upload_date_yt_dlp_writes_is_understood(self):
        """yt-dlp's `upload_date` is what DATE holds for every download."""
        self.assertEqual(format_release_date('20260903'), '03-09-2026')

    def test_a_timestamp_loses_its_time(self):
        self.assertEqual(format_release_date('2026-09-03T10:11:12'), '03-09-2026')

    def test_a_coarser_date_degrades_to_the_year(self):
        self.assertEqual(format_release_date('2026-00-00'), '2026')
        self.assertEqual(format_release_date('2026'), '2026')

    def test_nothing_usable_gives_none_so_the_line_is_left_out(self):
        self.assertIsNone(format_release_date(''))
        self.assertIsNone(format_release_date(None))
        self.assertIsNone(format_release_date('unknown'))


if __name__ == '__main__':
    unittest.main()
