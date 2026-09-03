"""Coverage for FestivalLineupBuilder: what a pasted bill turns into, and what it will match."""

import unittest

from services.common.Helpers.FestivalLineupBuilder import (
    lineup_filename,
    looks_like_an_artist,
    match_lineup,
    parse_lineup,
    render_lineup,
)


class LooksLikeAnArtistTest(unittest.TestCase):
    """A pasted bill carries page furniture along with the names."""

    def test_a_plain_name_is_an_artist(self):
        self.assertTrue(looks_like_an_artist('Angerfist'))

    def test_a_back_to_back_billing_is_kept(self):
        """The filter matches the whole display name, so a b2b line matches its own tracks and
        nothing else -- which is right, and is why it is not split."""
        self.assertTrue(looks_like_an_artist('Angerfist & Outsiders'))

    def test_a_date_is_not_a_name(self):
        self.assertFalse(looks_like_an_artist('2025-07-26'))

    def test_a_number_on_its_own_is_not(self):
        self.assertFalse(looks_like_an_artist('2025'))

    def test_blank_is_not(self):
        self.assertFalse(looks_like_an_artist('   '))
        self.assertFalse(looks_like_an_artist(None))

    def test_a_line_longer_than_a_name_is_not(self):
        self.assertFalse(looks_like_an_artist('A' * 121))


class ParseLineupTest(unittest.TestCase):
    """A bill is pasted, not typed one name at a time."""

    def test_keeps_the_order_of_the_bill(self):
        self.assertEqual(
            ['Angerfist', 'Rejecta', 'D-Block & S-te-Fan'],
            parse_lineup('Angerfist\nRejecta\nD-Block & S-te-Fan\n'),
        )

    def test_drops_blank_lines_and_debris(self):
        self.assertEqual(['Angerfist'], parse_lineup('Angerfist\n\n  \n2025\n2025-07-26\n'))

    def test_a_name_repeated_across_stages_is_written_once(self):
        self.assertEqual(['Angerfist'], parse_lineup('Angerfist\nangerfist\n'))


class MatchLineupTest(unittest.TestCase):
    """The exact-name match is the trap, so the report is the point of the whole tool."""

    known = ['Angerfist', 'D-Block & S-te-Fan', 'Rejecta', 'Angerfist & Outsiders']

    def test_a_name_the_library_has_matches(self):
        report = match_lineup(['Angerfist'], self.known)

        self.assertEqual(['Angerfist'], report['matched'])
        self.assertEqual([], report['unmatched'])

    def test_the_match_is_case_insensitive_and_reports_the_library_spelling(self):
        """`LOWER(artist_display_name) IN (...)` is case-insensitive, so the file may as well hold
        the spelling the browse page shows."""
        self.assertEqual(['Rejecta'], match_lineup(['REJECTA'], self.known)['matched'])

    def test_a_spelling_the_library_does_not_have_is_reported_with_the_ones_it_does(self):
        report = match_lineup(['D-Block and S-te-fan'], self.known)

        self.assertEqual(['D-Block and S-te-fan'], report['unmatched'])
        self.assertEqual(['D-Block & S-te-Fan'], report['suggestions']['D-Block and S-te-fan'])

    def test_a_name_nothing_resembles_gets_no_suggestion_rather_than_a_wrong_one(self):
        report = match_lineup(['Someone Else Entirely'], self.known)

        self.assertEqual(['Someone Else Entirely'], report['unmatched'])
        self.assertNotIn('Someone Else Entirely', report['suggestions'])

    def test_a_partial_billing_does_not_match_the_full_display_name(self):
        """This is the limitation the design names: the whole display name is compared, so an
        artist who only appears in a b2b is not reachable by their own name."""
        report = match_lineup(['Outsiders'], self.known)

        self.assertEqual(['Outsiders'], report['unmatched'])


class LineupFilenameTest(unittest.TestCase):
    """The file's stem is the name the app shows, so it is also the name a reader reads."""

    def test_an_edition_sits_under_the_festival(self):
        self.assertEqual('Defqon/2025.txt', lineup_filename('Defqon', '2025'))

    def test_without_a_year_the_festival_stands_alone(self):
        self.assertEqual('Defqon.txt', lineup_filename('Defqon'))

    def test_a_stage_sits_under_the_edition(self):
        self.assertEqual('Defqon.1/2014/RED.txt', lineup_filename('Defqon.1', '2014', 'RED'))

    def test_a_stage_without_a_year_is_refused(self):
        # There is nowhere to put it: the directory between the two is the edition.
        with self.assertRaises(ValueError):
            lineup_filename('Defqon.1', stage='RED')

    def test_a_separator_in_a_name_does_not_become_a_directory(self):
        self.assertEqual('AC-DC/2025.txt', lineup_filename('AC/DC', '2025'))
        self.assertEqual('Defqon/2014/RED-BLUE.txt', lineup_filename('Defqon', '2014', 'RED/BLUE'))

    def test_surrounding_whitespace_goes(self):
        self.assertEqual('Intents/2024.txt', lineup_filename('  Intents  ', '2024'))


class RenderLineupTest(unittest.TestCase):
    """`FestivalLineupRepository` reads every non-empty line as an artist -- there is no comment
    syntax, so a header would become an artist called '# generated'."""

    def test_one_name_per_line_and_a_closing_newline(self):
        self.assertEqual('Angerfist\nRejecta\n', render_lineup(['Angerfist', 'Rejecta']))

    def test_nothing_but_names(self):
        self.assertNotIn('#', render_lineup(['Angerfist']))


if __name__ == '__main__':
    unittest.main()
