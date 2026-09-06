import unittest

from services.tagger.Song.NfoTracklist import (
    describes_same_artists,
    entries,
    restorable_wording,
    split_artist_and_title,
    split_like_the_tagger,
)

# Layouts taken from real NFOs under /mnt/music/EPs, block art trimmed.
NUMBERED = """
                       ÛÛ²°   °²ÛÛ    ÛÛ²°  ²ÛÛ
   Tracklist
   01. JKLL - I Said What (Original Mix) [03:39]
   02. JKLL - Turn It Up (Original Mix) [03:53]
   03. JKLL Feat. AKSYS & Kickart - Feel Alive (Original Mix) [04:59]
"""

SINGLE = """
   RLS NAME : Eternate & Prosphere - Waiting For You
   LABEL    : Unlocked Records
"""


class EntriesTest(unittest.TestCase):
    def test_numbered_lines_are_read_with_their_number(self):
        found = entries(NUMBERED)
        self.assertEqual([1, 2, 3], [number for number, _a, _t in found])
        self.assertEqual('JKLL Feat. AKSYS & Kickart', found[2][1])
        self.assertEqual('Feel Alive (Original Mix)', found[2][2])

    def test_the_duration_is_not_part_of_the_title(self):
        self.assertEqual('I Said What (Original Mix)', entries(NUMBERED)[0][2])

    def test_a_release_header_is_read_without_a_number(self):
        found = entries(SINGLE)
        self.assertEqual([(None, 'Eternate & Prosphere', 'Waiting For You')], found)

    def test_block_art_yields_nothing(self):
        self.assertEqual([], entries('ÛÛ²°   °²ÛÛ    ÛÛ²°  ²ÛÛ\nÜÜÜÜÜÜÜ ÜÜ'))

    def test_empty_input_is_not_an_error(self):
        self.assertEqual([], entries(''))
        self.assertEqual([], entries(None))

    def test_a_title_may_contain_further_dashes(self):
        self.assertEqual(
            ('A-Kriv', 'Against Me - Extended Mix'), split_artist_and_title('A-Kriv - Against Me - Extended Mix')
        )

    def test_a_line_without_a_separator_is_not_a_track(self):
        self.assertIsNone(split_artist_and_title('Just Some Sentence'))


class SplitLikeTheTaggerTest(unittest.TestCase):
    """The guard is only trustworthy while this matches CleanTagsRule exactly."""

    def test_ampersand_splits(self):
        self.assertEqual(['Eternate', 'Prosphere'], split_like_the_tagger('Eternate & Prosphere'))

    def test_feat_splits(self):
        self.assertEqual(['JKLL', 'AKSYS', 'Kickart'], split_like_the_tagger('JKLL Feat. AKSYS & Kickart'))

    def test_a_single_name_stays_one_value(self):
        self.assertEqual(['Angerfist'], split_like_the_tagger('Angerfist'))


class GuardTest(unittest.TestCase):
    def test_same_artists_in_the_same_order_match(self):
        self.assertTrue(describes_same_artists('Eternate & Prosphere', ['Eternate', 'Prosphere']))

    def test_same_artists_in_a_different_order_still_match(self):
        self.assertTrue(describes_same_artists('Prosphere & Eternate', ['Eternate', 'Prosphere']))

    def test_case_does_not_break_the_match(self):
        self.assertTrue(describes_same_artists('eternate and PROSPHERE', ['Eternate', 'Prosphere']))

    def test_an_extra_artist_in_the_nfo_does_not_match(self):
        self.assertFalse(describes_same_artists('Eternate & Prosphere & Oxya', ['Eternate', 'Prosphere']))

    def test_a_missing_artist_does_not_match(self):
        self.assertFalse(describes_same_artists('Eternate', ['Eternate', 'Prosphere']))

    def test_a_different_artist_does_not_match(self):
        self.assertFalse(describes_same_artists('Hellfish & Akira', ['Eternate', 'Prosphere']))

    def test_empty_input_never_matches(self):
        self.assertFalse(describes_same_artists('', ['Eternate']))
        self.assertFalse(describes_same_artists('Eternate', []))


class RestorableWordingTest(unittest.TestCase):
    def test_the_wording_is_returned_when_it_adds_something(self):
        self.assertEqual(
            'Eternate & Prosphere',
            restorable_wording('Eternate & Prosphere', ['Eternate', 'Prosphere']),
        )

    def test_nothing_to_restore_when_the_nfo_repeats_the_stored_values(self):
        self.assertIsNone(restorable_wording('Eternate;Prosphere', ['Eternate', 'Prosphere']))

    def test_a_disagreeing_line_restores_nothing(self):
        self.assertIsNone(restorable_wording('Hellfish & Akira', ['Eternate', 'Prosphere']))

    def test_a_single_artist_track_has_no_wording_to_restore(self):
        self.assertIsNone(restorable_wording('Angerfist', ['Angerfist']))


if __name__ == '__main__':
    unittest.main()
