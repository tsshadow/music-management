"""Coverage for catalog_series: catalogue numbers taken apart and put into series.

The forms pinned here are the ones production actually holds: zero-padded numbers of
two widths inside one series (`DWX000` next to `DWX1000`), a digit inside the prefix
(`247HC`, `AFT3R`, `R909`), a separator before a two-digit number (`R909-29`), a
suffix that marks a variant (`DWX1105D`, `DWX0544-`), and a word with no number at all
(`DWXFREE`).
"""

import unittest

from services.music_manager.catalog_series import EXPANSION_CAP, build_catalog, parse_catid, runs

EPS = '/mnt/music/EPs'


def path(label: str, folder: str, file: str = '01-track.mp3') -> str:
    return f'{EPS}/{label}/{folder}/{file}'


def catalog(*folders: str, label: str = 'Dirty Workz') -> dict:
    return build_catalog([path(label, folder) for folder in folders], EPS, '/')


def series(summary: dict, prefix: str) -> dict:
    return next(entry for entry in summary['series'] if entry['prefix'] == prefix)


class ParseCatidTest(unittest.TestCase):
    def test_a_plain_zero_padded_number(self):
        parsed = parse_catid('DWX0001')
        self.assertEqual((parsed.prefix, parsed.number, parsed.digits, parsed.suffix), ('DWX', 1, '0001', ''))

    def test_a_suffix_marks_a_variant_but_keeps_the_number(self):
        self.assertEqual(parse_catid('DWX1105D').suffix, 'D')
        self.assertEqual(parse_catid('DWX1105D').number, 1105)
        self.assertEqual(parse_catid('DWX0544-').suffix, '-')
        self.assertEqual(parse_catid('DWX2149EPD').suffix, 'EPD')

    def test_a_separator_between_prefix_and_number_is_dropped_from_the_prefix(self):
        parsed = parse_catid('DWXCD-050')
        self.assertEqual((parsed.prefix, parsed.number, parsed.separator), ('DWXCD', 50, '-'))

    def test_digits_inside_the_prefix_do_not_end_it(self):
        self.assertEqual((parse_catid('247HC001').prefix, parse_catid('247HC001').number), ('247HC', 1))
        self.assertEqual((parse_catid('AFT3R001').prefix, parse_catid('AFT3R001').number), ('AFT3R', 1))

    def test_a_short_number_is_accepted_only_behind_a_separator(self):
        # Randy909 numbers its releases R909-29, R909-30, ... and later R909-049.
        parsed = parse_catid('R909-29')
        self.assertEqual((parsed.prefix, parsed.number, parsed.digits), ('R909', 29, '29'))
        self.assertEqual(parse_catid('R909-049').prefix, 'R909')
        self.assertIsNone(parse_catid('01'))

    def test_a_bare_number_has_an_empty_prefix(self):
        self.assertEqual((parse_catid('001').prefix, parse_catid('001').number), ('', 1))

    def test_the_prefix_is_upper_cased(self):
        self.assertEqual(parse_catid('dwx001').prefix, 'DWX')

    def test_nothing_numeric_is_not_a_catalogue_number(self):
        for catid in ('DWXFREE', 'Act', '', '   ', 'DWX-'):
            self.assertIsNone(parse_catid(catid), catid)


class RunsTest(unittest.TestCase):
    def test_consecutive_numbers_collapse_into_one_run(self):
        self.assertEqual(runs([1, 2, 3, 7, 10, 11]), [[1, 3], [7, 7], [10, 11]])

    def test_nothing_absent_is_no_runs(self):
        self.assertEqual(runs([]), [])


class BuildCatalogTest(unittest.TestCase):
    def test_absent_numbers_are_the_holes_between_min_and_max(self):
        summary = catalog('DWX0001 A', 'DWX0002 B', 'DWX0003 C', 'DWX0005 E', 'DWX0009 I')
        dwx = series(summary, 'DWX')
        self.assertEqual((dwx['min'], dwx['max'], dwx['present'], dwx['releases']), (1, 9, 5, 5))
        self.assertEqual(dwx['absent'], [4, 6, 7, 8])
        self.assertEqual(dwx['absent_runs'], [[4, 4], [6, 8]])
        self.assertEqual(dwx['absent_count'], 4)
        self.assertEqual(dwx['coverage'], round(5 / 9, 3))
        self.assertFalse(dwx['absent_truncated'])
        self.assertEqual(dwx['width'], 4)
        self.assertEqual(dwx['separator'], '')

    def test_nothing_is_claimed_before_min_or_after_max(self):
        summary = catalog('DWX0300 A', 'DWX0301 B')
        self.assertEqual(series(summary, 'DWX')['absent'], [])
        self.assertEqual(series(summary, 'DWX')['coverage'], 1.0)

    def test_several_files_of_one_release_count_once(self):
        paths = [path('Dirty Workz', 'DWX0001 A', f'{n:02d}-track.mp3') for n in range(1, 5)]
        summary = build_catalog(paths, EPS, '/')
        self.assertEqual(summary['files_considered'], 4)
        self.assertEqual(series(summary, 'DWX')['releases'], 1)

    def test_a_variant_fills_its_position_and_is_reported(self):
        summary = catalog('DWX1104 A', 'DWX1105D B', 'DWX1106 C')
        dwx = series(summary, 'DWX')
        self.assertEqual(dwx['present'], 3)
        self.assertEqual(dwx['absent'], [])
        self.assertEqual(dwx['variants'], [{'catid': 'DWX1105D', 'release_folder': 'DWX1105D B'}])

    def test_a_plain_release_and_its_variant_are_one_position_two_releases(self):
        summary = catalog('DWX1105 A', 'DWX1105D B')
        dwx = series(summary, 'DWX')
        self.assertEqual((dwx['present'], dwx['releases']), (1, 2))

    def test_a_dash_suffix_is_a_variant_too(self):
        summary = catalog('DWX0544- A')
        self.assertEqual(series(summary, 'DWX')['variants'][0]['catid'], 'DWX0544-')

    def test_unreadable_numbers_go_to_other_and_never_widen_a_series(self):
        summary = catalog('DWX0001 A', 'DWX0002 B', 'DWXFREE Some Freebie')
        self.assertEqual(series(summary, 'DWX')['max'], 2)
        self.assertEqual(summary['other'], [{'catid': 'DWXFREE', 'release_folder': 'DWXFREE Some Freebie'}])

    def test_a_separated_number_lands_in_the_same_series_as_its_unseparated_siblings(self):
        summary = catalog('DWXCD001 A', 'DWXCD002 B', 'DWXCD-050 C')
        dwxcd = series(summary, 'DWXCD')
        self.assertEqual((dwxcd['min'], dwxcd['max'], dwxcd['present']), (1, 50, 3))
        self.assertEqual(dwxcd['separator'], '')

    def test_a_series_that_always_separates_reports_the_separator(self):
        summary = catalog('R909-29 A', 'R909-30 B', 'R909-32 C', label='Randy909')
        r909 = series(summary, 'R909')
        self.assertEqual((r909['separator'], r909['width'], r909['absent']), ('-', 2, [31]))

    def test_digits_in_the_prefix_keep_the_series_together(self):
        summary = catalog('247HC001 A', '247HC003 B', label='247 Hardcore')
        self.assertEqual(series(summary, '247HC')['absent'], [2])
        summary = catalog('AFT3R000 A', 'AFT3R002 B', label='Afterlife')
        self.assertEqual(series(summary, 'AFT3R')['absent'], [1])

    def test_sibling_prefixes_are_separate_series(self):
        summary = catalog('ACT001 A', 'ACTSE001 B', 'ACTDIG001 C', label='Activa')
        self.assertEqual(sorted(entry['prefix'] for entry in summary['series']), ['ACT', 'ACTDIG', 'ACTSE'])

    def test_two_widths_in_one_series_pad_to_the_more_common_one_ties_going_wider(self):
        summary = catalog('DWX000 A', 'DWX0999 B')
        dwx = series(summary, 'DWX')
        self.assertEqual((dwx['min'], dwx['max'], dwx['present'], dwx['width']), (0, 999, 2, 4))
        self.assertEqual(dwx['absent_count'], 998)
        self.assertEqual(dwx['absent_runs'], [[1, 998]])
        summary = catalog('DWX000 A', 'DWX001 B', 'DWX0999 C')
        self.assertEqual(series(summary, 'DWX')['width'], 3)

    def test_case_differences_do_not_split_a_series(self):
        summary = catalog('dwx001 A', 'DWX003 B')
        self.assertEqual(len(summary['series']), 1)
        self.assertEqual(series(summary, 'DWX')['absent'], [2])

    def test_series_are_ordered_by_how_much_is_present(self):
        summary = catalog('DWXCD001 A', 'DWX001 B', 'DWX002 C', 'DWX003 D')
        self.assertEqual([entry['prefix'] for entry in summary['series']], ['DWX', 'DWXCD'])

    def test_an_outlier_that_makes_the_span_huge_is_reported_by_count_only(self):
        summary = catalog('DWX0001 A', 'DWX0002 B', f'DWX{EXPANSION_CAP + 5} typo')
        dwx = series(summary, 'DWX')
        self.assertTrue(dwx['absent_truncated'])
        self.assertEqual(dwx['absent'], [])
        self.assertEqual(dwx['absent_runs'], [])
        self.assertEqual(dwx['absent_count'], EXPANSION_CAP + 5 - 3)
        self.assertEqual(dwx['present'], 3)

    def test_a_span_exactly_at_the_cap_is_still_enumerated(self):
        summary = catalog('DWX00001 A', f'DWX{EXPANSION_CAP:05d} B')
        self.assertFalse(series(summary, 'DWX')['absent_truncated'])
        self.assertEqual(len(series(summary, 'DWX')['absent']), EXPANSION_CAP - 2)

    def test_bare_numbers_form_a_series_with_an_empty_prefix(self):
        summary = catalog('000 A', '002 B', label='Black Reaper Records')
        self.assertEqual(series(summary, '')['absent'], [1])

    def test_a_nested_release_folder_is_read_from_the_eps_root_not_from_the_file(self):
        nested = f'{EPS}/Dirty Workz/DWX0001 A/DWX0001 A/01-track.mp3'
        summary = build_catalog([nested, path('Dirty Workz', 'DWX0003 C')], EPS, '/')
        self.assertEqual(series(summary, 'DWX')['absent'], [2])

    def test_a_path_outside_the_eps_root_is_skipped_and_counted(self):
        # The label link also brings in Soundcloud/, Podcasts/ and Top 100/ files, where
        # the folder above the file is a channel or a show. A channel named `Set 2019`
        # would otherwise become a series; a channel named `Dirty Workz` would land in
        # `other`. Neither says anything about the catalogue.
        paths = [
            path('Dirty Workz', 'DWX0001 A'),
            '/mnt/music/Soundcloud/Dirty Workz/some-set.mp3',
            '/mnt/music/Podcasts/Show 2019/episode.mp3',
            '/mnt/music/Top 100/2019/track.mp3',
        ]
        summary = build_catalog(paths, EPS, '/')
        self.assertEqual((summary['files_considered'], summary['files_outside_root']), (4, 3))
        self.assertEqual([entry['prefix'] for entry in summary['series']], ['DWX'])
        self.assertEqual(summary['other'], [])

    def test_a_folder_that_merely_starts_with_the_root_name_is_outside_it(self):
        summary = build_catalog([f'{EPS}2/Dirty Workz/DWX0001 A/01.mp3'], EPS, '/')
        self.assertEqual(summary['files_outside_root'], 1)

    def test_without_a_configured_root_the_two_folders_above_the_file_are_used(self):
        summary = build_catalog(['/import/Dirty Workz/DWX0007 G/01.mp3'], '', '/')
        self.assertEqual(series(summary, 'DWX')['min'], 7)
        self.assertEqual(summary['files_outside_root'], 0)

    def test_a_file_directly_in_the_label_folder_is_counted_but_not_read(self):
        summary = build_catalog([f'{EPS}/Dirty Workz/loose.mp3', path('Dirty Workz', 'DWX0001 A')], EPS, '/')
        self.assertEqual(summary['files_considered'], 2)
        self.assertEqual(series(summary, 'DWX')['releases'], 1)
        self.assertEqual(summary['other'], [])

    def test_no_files_is_an_empty_catalogue(self):
        self.assertEqual(
            build_catalog([], EPS, '/'), {'files_considered': 0, 'files_outside_root': 0, 'series': [], 'other': []}
        )
