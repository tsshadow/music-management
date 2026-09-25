"""Characterisation of every name/text normalizer in the tree, on one table of tricky inputs.

Written before the normalizers were consolidated into `services.common.text_normalize`
(docs/bug-reports/084-unused-endpoints-and-duplicate-normalizers.md) and kept as the guard
afterwards: each table below is the exact output the implementation had at the time, so a
refactor that changes one call site's behaviour goes red here.

Implementations that share a table are behaviourally identical on it -- that is the evidence
the consolidation rests on. The ones with a table of their own differ on purpose; the
docstring of each says why.
"""

import unittest

from services.common import text_normalize
from services.common.Helpers import ArtistNameAnalyzer, GenreNameAnalyzer, PodcastHelper
from services.common.Helpers.FestivalHelper import FestivalHelper
from services.common.Helpers.GenreRulesHelper import GenreRulesHelper
from services.music_manager import curation_rules, scrobble_matching
from services.music_manager.artist_image_fetcher.normalizer import ArtistNameNormalizer
from services.tagger.Song.Tag import Tag

#: One input per trap: casing, accents, a letter NFKD cannot decompose (Ø, ß), `&` and the
#: spellings of "featuring", double and edge whitespace, a leading "The", emoji, a non-Latin
#: script, underscores, intra-word punctuation, a zero-width space, a ligature and a Roman
#: numeral that NFKD rewrites.
INPUTS = [
    '',
    None,
    'Hardstyle',
    'HARD  Style',
    '  Ran-D  ',
    'Frenchcore & Terror',
    'Artist feat. Other',
    'Artist ft. Other',
    'Artist featuring Other',
    'Beyoncé',
    'Øystein Sevåg',
    'Straße',
    'Don’t Stop',
    "Don't Stop",
    'The Prophet',
    'Headhunterz 🔥',
    'Дмитрий',
    'Q-dance_Records',
    'Scantraxx Official',
    'A.B.C.',
    'Mr. Ivex',
    'x​y',
    'ﬁne',
    'Ⅳ',
]

#: ASCII key: genres, shows, the curation page. Every non-[a-z0-9] character is a separator,
#: so Ø, ß and whole non-Latin names fall away.
GENRE_KEY = [
    '',
    '',
    'hardstyle',
    'hard style',
    'ran d',
    'frenchcore terror',
    'artist feat other',
    'artist ft other',
    'artist featuring other',
    'beyonce',
    'ystein sevag',
    'stra e',
    'don t stop',
    'don t stop',
    'the prophet',
    'headhunterz',
    '',
    'q dance records',
    'scantraxx official',
    'a b c',
    'mr ivex',
    'x y',
    'fine',
    'iv',
]

#: Unicode key: artists. Same shape as GENRE_KEY, but any alphanumeric in any script stays.
ARTIST_KEY = [
    '',
    '',
    'hardstyle',
    'hard style',
    'ran d',
    'frenchcore terror',
    'artist feat other',
    'artist ft other',
    'artist featuring other',
    'beyonce',
    'øystein sevag',
    'straße',
    'don t stop',
    'don t stop',
    'the prophet',
    'headhunterz',
    'дмитрии',
    'q dance records',
    'scantraxx official',
    'a b c',
    'mr ivex',
    'x y',
    'fine',
    'iv',
]

#: Scrobble matching: casefold (ß -> ss), "feat."/"ft."/"featuring" folded away, intra-word
#: apostrophes and dots deleted, `_` kept as a word character.
SCROBBLE_KEY = [
    '',
    '',
    'hardstyle',
    'hard style',
    'ran d',
    'frenchcore terror',
    'artist other',
    'artist other',
    'artist other',
    'beyonce',
    'øystein sevag',
    'strasse',
    'dont stop',
    'dont stop',
    'the prophet',
    'headhunterz',
    'дмитрии',
    'q dance_records',
    'scantraxx official',
    'abc',
    'mr ivex',
    'x y',
    'fine',
    'iv',
]

#: Artist image fetcher: lower case, `_`/`-` as spaces, platform suffixes cut, nothing else.
IMAGE_FETCHER_KEY = [
    '',
    '',
    'hardstyle',
    'hard style',
    'ran d',
    'frenchcore & terror',
    'artist feat. other',
    'artist ft. other',
    'artist featuring other',
    'beyoncé',
    'øystein sevåg',
    'straße',
    'don’t stop',
    "don't stop",
    'the prophet',
    'headhunterz 🔥',
    'дмитрий',
    'q dance',
    'scantraxx',
    'a.b.c.',
    'mr. ivex',
    'x​y',
    'ﬁne',
    'ⅳ',
]


class NormalizerCharacterisationTest(unittest.TestCase):
    """Each implementation, pinned to the output it had before consolidation."""

    def assert_table(self, fn, expected, wrap=lambda value: value):
        self.assertEqual(len(INPUTS), len(expected))
        for value, want in zip(INPUTS, expected, strict=True):
            with self.subTest(input=value):
                self.assertEqual(fn(value), wrap(want))

    def test_the_genre_key_family_is_one_behaviour(self):
        for fn in (
            GenreRulesHelper.normalize,
            GenreNameAnalyzer.normalize,
            PodcastHelper.normalize,
            curation_rules.normalize_genre,
            text_normalize.ascii_name_key,
        ):
            with self.subTest(implementation=f'{fn.__module__}.{fn.__qualname__}'):
                self.assert_table(fn, GENRE_KEY)

    def test_the_padded_variants_are_the_genre_key_between_spaces(self):
        for fn in (FestivalHelper.normalize, PodcastHelper.padded, text_normalize.padded_ascii_name_key):
            with self.subTest(implementation=f'{fn.__module__}.{fn.__qualname__}'):
                self.assert_table(fn, GENRE_KEY, wrap=lambda value: f' {value} ')

    def test_the_artist_key_keeps_every_script(self):
        for fn in (ArtistNameAnalyzer.normalize, text_normalize.unicode_name_key):
            with self.subTest(implementation=f'{fn.__module__}.{fn.__qualname__}'):
                self.assert_table(fn, ARTIST_KEY)

    def test_the_scrobble_key_folds_featuring_and_apostrophes(self):
        self.assert_table(scrobble_matching.normalize, SCROBBLE_KEY)

    def test_the_image_fetcher_key_only_trims_platform_noise(self):
        self.assert_table(ArtistNameNormalizer.normalize, IMAGE_FETCHER_KEY)

    def test_the_artist_squash_key_is_the_artist_key_without_spaces(self):
        self.assertEqual(ArtistNameAnalyzer._squash('Ran-D & Adaro'), 'randadaro')


class TagSetNormalizeTest(unittest.TestCase):
    """`Tag.set`'s inner `normalize` is a list cleaner, not a name key: strip, drop empties."""

    def test_values_are_stripped_and_empty_entries_dropped(self):
        tag = Tag('genre', 'Hardstyle')
        tag.set(' Hardstyle ;  ; Rawstyle ')
        self.assertEqual(tag.value, ['Hardstyle', 'Rawstyle'])

    def test_casing_accents_and_punctuation_are_left_alone(self):
        tag = Tag('artist', 'x')
        tag.set(['  Beyoncé ', 'Ran-D', ''])
        self.assertEqual(tag.value, ['Beyoncé', 'Ran-D'])


if __name__ == '__main__':
    unittest.main()
