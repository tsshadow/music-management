"""Coverage for FestivalLineupBuilder: which names are an artist, and what a lineup file holds."""

import unittest

from services.common.Helpers.FestivalLineupBuilder import (
    build_editions,
    lineup_filename,
    looks_like_an_artist,
    render_lineup,
)


class LooksLikeAnArtistTest(unittest.TestCase):
    """The display names in the library include debris the tagger left behind."""

    def test_a_plain_name_is_an_artist(self):
        self.assertTrue(looks_like_an_artist('Angerfist'))

    def test_a_back_to_back_billing_is_kept(self):
        """`allowedArtists` matches the whole display name, so a b2b line matches its own tracks
        and nothing else -- which is right, and is why it is not split or dropped."""
        self.assertTrue(looks_like_an_artist('Aalst, Deviation'))

    def test_a_name_that_is_a_date_is_not(self):
        self.assertFalse(looks_like_an_artist('1 2025 2025-10-24 18'))

    def test_a_number_on_its_own_is_not(self):
        self.assertFalse(looks_like_an_artist('2025'))

    def test_blank_is_not(self):
        self.assertFalse(looks_like_an_artist('   '))
        self.assertFalse(looks_like_an_artist(None))

    def test_a_name_longer_than_a_name_is_not(self):
        """A whole tracklist ends up in the artist field often enough to be worth a ceiling."""
        self.assertFalse(looks_like_an_artist('A' * 121))


class BuildEditionsTest(unittest.TestCase):
    """One edition per festival and year, and only when there is a bill to speak of."""

    rows = [
        ('Defqon', '2025', 'Angerfist'),
        ('Defqon', '2025', 'D-Block & S-te-Fan'),
        ('Defqon', '2025', 'Angerfist'),
        ('Defqon', '2025', 'Rejecta'),
        ('Defqon', '2024', 'Angerfist'),
        ('Decibel', '2024', '1 2025 2025-10-24 18'),
    ]

    def test_groups_by_festival_and_year_and_deduplicates(self):
        editions = build_editions(self.rows, min_artists=3)

        self.assertEqual([('Defqon', '2025')], list(editions))
        self.assertEqual(['Angerfist', 'D-Block & S-te-Fan', 'Rejecta'], editions[('Defqon', '2025')])

    def test_an_edition_below_the_floor_is_left_out(self):
        """Two names is a coincidence, not a lineup, and an almost-empty page is worse than none."""
        self.assertNotIn(('Defqon', '2024'), build_editions(self.rows, min_artists=3))

    def test_debris_is_dropped_before_the_floor_is_applied(self):
        self.assertNotIn(('Decibel', '2024'), build_editions(self.rows, min_artists=1))

    def test_a_row_without_a_usable_year_is_skipped(self):
        rows = [('Defqon', None, 'Angerfist'), ('Defqon', 'onbekend', 'Rejecta')]
        self.assertEqual({}, build_editions(rows, min_artists=1))


class LineupFilenameTest(unittest.TestCase):
    """The file's stem is the name the app shows, so it is also the name a reader reads."""

    def test_the_stem_is_the_festival_and_the_year(self):
        self.assertEqual('Defqon 2025.txt', lineup_filename('Defqon', '2025'))

    def test_a_separator_in_the_name_does_not_become_a_directory(self):
        self.assertEqual('AC-DC 2025.txt', lineup_filename('AC/DC', '2025'))

    def test_surrounding_whitespace_goes(self):
        self.assertEqual('Intents 2024.txt', lineup_filename('  Intents  ', '2024'))


class RenderLineupTest(unittest.TestCase):
    """`FestivalLineupRepository` reads every non-empty line as an artist -- there is no comment
    syntax, so a header would become an artist called '# generated'."""

    def test_one_name_per_line_and_a_closing_newline(self):
        self.assertEqual('Angerfist\nRejecta\n', render_lineup(['Angerfist', 'Rejecta']))

    def test_nothing_but_names(self):
        rendered = render_lineup(['Angerfist'])
        self.assertNotIn('#', rendered)


if __name__ == '__main__':
    unittest.main()
