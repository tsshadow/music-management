import os
import tempfile
import unittest
from datetime import date

from services.tagger.Song import NfoDate


class DirnameTest(unittest.TestCase):
    def test_takes_the_last_year_so_a_catalogue_year_does_not_win(self):
        name = 'Official_Archive_2023_Anthem - Shockwave_-_Nothing-WEB-2024-ZzZz'
        self.assertEqual(NfoDate.dirname_year(name), 2024)

    def test_ignores_a_year_embedded_in_a_longer_digit_run(self):
        name = 'AVR2026006BP - Untold_Stories_-_To_The_Top-(AVR2026006BP)-WEB-2025'
        self.assertEqual(NfoDate.dirname_year(name), 2025)

    def test_returns_none_without_a_year(self):
        self.assertIsNone(NfoDate.dirname_year('Some_Bootleg_Folder'))

    def test_scene_group_is_the_token_after_the_year(self):
        self.assertEqual(NfoDate.scene_group('Quickdrop_-_You_Got_Me-(1035)-WEB-2026-ZzZz'), 'ZzZz')

    def test_scene_group_is_none_when_the_year_ends_the_name(self):
        self.assertIsNone(NfoDate.scene_group('Masters_Of_Noise_-_What_My_Name_Is-(0036)-WEB-2026'))


class TokenOrderTest(unittest.TestCase):
    def test_a_component_above_twelve_fixes_the_day(self):
        self.assertEqual(NfoDate.resolve_token('17.10.2025'), date(2025, 10, 17))

    def test_a_component_above_twelve_wins_over_a_conflicting_override(self):
        self.assertEqual(NfoDate.resolve_token('17.10.2025', NfoDate.MONTH_DAY), date(2025, 10, 17))

    def test_year_last_defaults_to_day_then_month(self):
        self.assertEqual(NfoDate.resolve_token('05.06.2026'), date(2026, 6, 5))

    def test_year_first_defaults_to_month_then_day(self):
        self.assertEqual(NfoDate.resolve_token('2026-01-02'), date(2026, 1, 2))

    def test_an_override_beats_the_positional_default(self):
        self.assertEqual(NfoDate.resolve_token('05.06.2026', NfoDate.MONTH_DAY), date(2026, 5, 6))

    def test_an_impossible_date_falls_back_to_the_other_order(self):
        # 29 cannot be a month, so 02.29.2024 is February 29th however the group usually writes it.
        self.assertEqual(NfoDate.resolve_token('02.29.2024'), date(2024, 2, 29))

    def test_a_date_impossible_in_both_orders_is_rejected(self):
        self.assertIsNone(NfoDate.resolve_token('13.13.2024'))

    def test_a_token_without_a_four_digit_year_is_rejected(self):
        self.assertIsNone(NfoDate.resolve_token('05.06.26'))

    def test_february_thirtieth_is_rejected_rather_than_clamped(self):
        self.assertIsNone(NfoDate.resolve_token('30.02.2024'))


class ResolveTest(unittest.TestCase):
    def test_street_date_beats_rip_date(self):
        text = 'Str.date : 16-01-2026\nRip.date : 20-01-2026\n'
        kind, resolved = NfoDate.resolve(text, 'X_-_Y-(008R017)-WEB-2026-ZzZz')
        self.assertEqual(kind, 'street')
        self.assertEqual(resolved, date(2026, 1, 16))

    def test_rip_date_is_used_when_there_is_no_street_date(self):
        kind, resolved = NfoDate.resolve('RIP DATE[ 01-09-2025', 'X_-_Y-(HCL104)-WEB-2025-SRG')
        self.assertEqual(kind, 'rip')
        self.assertEqual(resolved, date(2025, 9, 1))

    def test_a_year_mismatch_is_rejected(self):
        """A 1995 vinyl rip carrying a 2024 rip date must not become a 2024 release."""
        kind, resolved = NfoDate.resolve('Date: 2024-07-28', 'Dyewitness-Battle-(MIDLP1)-VINYL-FLAC-1995-OTS')
        self.assertIsNone(kind)
        self.assertIsNone(resolved)

    def test_a_second_candidate_is_tried_after_a_year_mismatch(self):
        text = 'Str.date : 06.05.2024\nRip.date : 11.05.2014\n'
        kind, resolved = NfoDate.resolve(text, 'Kurwastyle_Project-Lost_In_Society-KCRCD002-WEB-2014-XTC')
        self.assertEqual(kind, 'rip')
        self.assertEqual(resolved, date(2014, 5, 11))

    def test_a_directory_without_a_year_yields_nothing(self):
        kind, resolved = NfoDate.resolve('Str.date : 16-01-2026', 'Some_Bootleg_Folder')
        self.assertIsNone(kind)
        self.assertIsNone(resolved)

    def test_no_date_at_all_yields_nothing(self):
        kind, resolved = NfoDate.resolve('nothing useful here', 'X-WEB-2026-ZzZz')
        self.assertIsNone(kind)
        self.assertIsNone(resolved)


class ReadNfoTest(unittest.TestCase):
    def test_reads_cp437_art_and_strips_nul_bytes(self):
        raw = b'\xdb\xdc art \x00\x00 Str.date\xfe\xfe: 16-01-2026\r\n'
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, '00-release.nfo'), 'wb') as handle:
                handle.write(raw)
            text = NfoDate.read_nfo(directory)
        self.assertIsNotNone(text)
        self.assertNotIn('\x00', text)
        self.assertIn('16-01-2026', text)

    def test_returns_none_without_an_nfo(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(NfoDate.read_nfo(directory))

    def test_returns_none_for_a_missing_directory(self):
        self.assertIsNone(NfoDate.read_nfo('/nonexistent/path/for/this/test'))


if __name__ == '__main__':
    unittest.main()
