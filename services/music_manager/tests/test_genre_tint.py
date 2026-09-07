"""The colour a genre is drawn in.

Both clients draw a genre as a coloured tile, and they must agree: Hardstyle orange in the web UI
and magenta in the app is the kind of difference nobody notices until both are open side by side.
Deriving the colour on the server means neither client owns a table that can drift.
"""

import unittest

from services.music_manager.genre_tint import genre_tint


class NamedGenresTest(unittest.TestCase):
    def test_the_genres_the_collection_is_built_on_have_a_chosen_colour(self):
        # Hardstyle is not a hash away from whatever hue it lands on: it is the genre that carries
        # this collection, and it gets the orange that the festivals it comes from use.
        self.assertEqual(genre_tint('Hardstyle'), '#ff4d00')

    def test_the_lookup_ignores_case_and_surrounding_space(self):
        self.assertEqual(genre_tint('  HARDSTYLE '), genre_tint('hardstyle'))


class DerivedGenresTest(unittest.TestCase):
    def test_a_genre_nobody_named_still_gets_a_colour(self):
        tint = genre_tint('Frenchcore')
        self.assertRegex(tint, r'^#[0-9a-f]{6}$')

    def test_the_same_name_always_gets_the_same_colour(self):
        # The clients cache these. A colour that moved between two calls would make a genre change
        # colour halfway down a list.
        self.assertEqual(genre_tint('Frenchcore'), genre_tint('Frenchcore'))

    def test_two_different_names_do_not_collapse_onto_one_colour(self):
        self.assertNotEqual(genre_tint('Frenchcore'), genre_tint('Jumpstyle'))

    def test_the_derived_colour_is_bright_enough_to_carry_black_text(self):
        # The tile prints the genre name in near-black over this colour. A dark derived tint would
        # make exactly the unnamed genres unreadable.
        red, green, blue = _rgb(genre_tint('Frenchcore'))
        self.assertGreater(max(red, green, blue), 200)

    def test_the_derived_colour_is_saturated_rather_than_grey(self):
        red, green, blue = _rgb(genre_tint('Frenchcore'))
        self.assertGreater(max(red, green, blue) - min(red, green, blue), 80)


class EmptyNameTest(unittest.TestCase):
    def test_a_missing_name_gets_the_fallback_rather_than_an_error(self):
        # Genre names reach this from tags, and a blank one has shown up before. A tile without a
        # colour is worse than a tile in the neutral one.
        self.assertRegex(genre_tint(''), r'^#[0-9a-f]{6}$')
        self.assertEqual(genre_tint(''), genre_tint(None))


def _rgb(tint: str) -> tuple[int, int, int]:
    return int(tint[1:3], 16), int(tint[3:5], 16), int(tint[5:7], 16)


if __name__ == '__main__':
    unittest.main()
