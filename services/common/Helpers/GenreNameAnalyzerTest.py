"""The real examples from the curation queue are the specification here.

Every case in `RealWorldExamplesTest` is a name taken from the production queue
(821 entries on 2026-09-18) with the outcome the dry run was tuned to give, and
the dictionary is a slice of the real approved list and its corrections.
"""

import unittest

from services.common.Helpers.GenreNameAnalyzer import (
    KEEP,
    REJECT,
    REWRITE,
    SPLIT,
    UNKNOWN,
    GenreAnalyzerConfig,
    GenreDictionary,
    GenreNameAnalyzer,
    build_dictionary,
    normalize,
)

APPROVED = [
    ('Hardstyle', 35669),
    ('Hardcore', 34867),
    ('Raw Hardstyle', 17115),
    ('Uptempo Hardcore', 14046),
    ('Techno', 9792),
    ('Euphoric Hardstyle', 3792),
    ('Frenchcore', 3072),
    ('Terror', 1605),
    ('Industrial Hardcore', 1514),
    ('Hard Techno', 1305),
    ('Happy Hardcore', 1054),
    ('Trance', 658),
    ('Hardcore Techno', 648),
    ('Rock', 469),
    ('Early Hardcore', 115),
    ('Hard', 70),
    ('Jungle', 36),
    ('Oldschool', 35),
    ('Core', 33),
    ('Electronic', 20),
    ('Tek', 21),
    ('Metal', 199),
    ('Melodic House', 211),
    ('Future Bass', 132),
    ('Speedcore', 143),
    ('Uplifting Trance', 5),
    ('Zaagtempo', 1125),
    # White but corrected: the tagger writes the target, never this spelling.
    ('RAW', 0),
    ('Upterror', 0),
    ('Vocal Trance', 0),
    # Legacy `;`-joined target name.
    ('Uptempo Hardcore;Terror', 0),
]
EXPANSIONS = [
    ('RAW', 'Raw Hardstyle'),
    ('Upterror', 'Uptempo Hardcore;Terror'),
    ('Vocal Trance', 'Trance'),
    ('uptempo', 'Uptempo Hardcore'),
    ('Dnb', "Drum 'N Bass"),  # target not approved: the alias must not survive
    ('Hardstyle 2018', 'Hardstyle'),
    ('Gym Hardstyle', 'Hardstyle'),
]
REJECTED = ['HEARTBREAK', 'Fvckgenres', 'sample']
ARTISTS = [('Henry Fong', None), ('Dr Peacock', 'Frenchcore'), ('Melodic', None), ('Future', None)]
LABELS = [('Scarred Digital', None), ('Snakepit Music', 'Uptempo Hardcore')]


def analyzer(**overrides) -> GenreNameAnalyzer:
    return GenreNameAnalyzer(
        build_dictionary(APPROVED, EXPANSIONS, REJECTED, ARTISTS, LABELS),
        GenreAnalyzerConfig(**overrides) if overrides else None,
    )


class NormalizeTest(unittest.TestCase):
    def test_matches_the_tagger_key(self):
        self.assertEqual(normalize('  RAW/HARDSTYLE  '), 'raw hardstyle')
        self.assertEqual(normalize('Frenchcöre'), 'frenchcore')
        self.assertEqual(normalize('***'), '')


class BuildDictionaryTest(unittest.TestCase):
    def setUp(self):
        self.dictionary = build_dictionary(APPROVED, EXPANSIONS, REJECTED, ARTISTS, LABELS)

    def test_an_approved_genre_with_a_correction_is_an_alias_not_a_target(self):
        self.assertNotIn('RAW', self.dictionary.approved)
        self.assertEqual(self.dictionary.aliases['RAW'], ['Raw Hardstyle'])

    def test_a_joined_target_name_resolves_to_its_parts(self):
        self.assertNotIn('Uptempo Hardcore;Terror', self.dictionary.approved)
        self.assertEqual(self.dictionary.aliases['Upterror'], ['Uptempo Hardcore', 'Terror'])

    def test_an_alias_whose_target_is_not_approved_is_dropped(self):
        self.assertNotIn('Dnb', self.dictionary.aliases)

    def test_popularity_is_kept_for_ranking(self):
        self.assertEqual(self.dictionary.approved['Hardstyle'], 35669)

    def test_rejected_artists_and_labels_are_carried_over(self):
        self.assertIn('HEARTBREAK', self.dictionary.rejected)
        self.assertEqual(self.dictionary.artists['Dr Peacock'], 'Frenchcore')
        self.assertIsNone(self.dictionary.labels['Scarred Digital'])


class RealWorldExamplesTest(unittest.TestCase):
    def setUp(self):
        self.analyzer = analyzer()

    def propose(self, name):
        return self.analyzer.propose(name)

    def test_an_approved_spelling_is_kept(self):
        proposal = self.propose('Hardcore')
        self.assertEqual((proposal.kind, proposal.values), (KEEP, ['Hardcore']))

    def test_a_name_already_corrected_gets_the_same_correction(self):
        proposal = self.propose('UPTEMPO')
        self.assertEqual((proposal.kind, proposal.values), (REWRITE, ['Uptempo Hardcore']))
        self.assertIn('already decided', proposal.evidence[0])

    def test_the_same_name_without_spaces_is_a_rewrite(self):
        proposal = self.propose('Uptempohardcore')
        self.assertEqual((proposal.kind, proposal.values, proposal.confidence), (REWRITE, ['Uptempo Hardcore'], 95))
        self.assertEqual(self.propose('Futurebass').values, ['Future Bass'])
        self.assertEqual(self.propose('Old School').values, ['Oldschool'])

    def test_a_slash_splits_into_the_genres_on_either_side(self):
        proposal = self.propose('Frenchcore/Terror')
        self.assertEqual((proposal.kind, proposal.values, proposal.confidence), (SPLIT, ['Frenchcore', 'Terror'], 90))

    def test_other_separators_split_too(self):
        self.assertEqual(self.propose('TECHNO / HARD TECHNO').values, ['Techno', 'Hard Techno'])
        self.assertEqual(self.propose('Hardcore\\ Industrial Hardcore').values, ['Hardcore', 'Industrial Hardcore'])
        self.assertEqual(self.propose('Electronic,Hardstyle').values, ['Electronic', 'Hardstyle'])
        self.assertEqual(self.propose('Hardstyle en Hardcore').values, ['Hardstyle', 'Hardcore'])

    def test_a_split_part_that_matches_nothing_is_dropped_with_lower_confidence(self):
        proposal = self.propose('Hardcore/Drill')
        self.assertEqual((proposal.kind, proposal.values, proposal.confidence), (SPLIT, ['Hardcore'], 60))
        self.assertIn('dropped: Drill', proposal.evidence[-1])

    def test_a_split_part_that_reads_as_a_genre_blocks_the_advice(self):
        proposal = self.propose('Hardstyle / Hardbass')
        self.assertEqual(proposal.kind, UNKNOWN)
        self.assertIn("'Hardbass' reads as a genre too", proposal.evidence[-1])

    def test_a_list_that_is_mostly_unknown_gets_no_split(self):
        proposal = self.propose('Edit,Fatico,Splintr,Säge,Terror')
        self.assertNotEqual(proposal.kind, SPLIT)

    def test_a_stray_trailing_slash_is_cleaned(self):
        proposal = self.propose('Harddcore/')
        self.assertEqual((proposal.kind, proposal.values, proposal.confidence), (REWRITE, ['Hardcore'], 90))
        self.assertIn('stray separator', proposal.evidence[0])

    def test_a_blend_is_the_start_of_one_genre_and_the_whole_of_another(self):
        """`Upterror` is what the maintainer means by a contraction."""
        fresh = GenreNameAnalyzer(build_dictionary(APPROVED[:-5], [], [], [], []))
        proposal = fresh.propose('Upterror')
        self.assertEqual((proposal.kind, proposal.values), (SPLIT, ['Uptempo Hardcore', 'Terror']))
        self.assertIn("'up' begins Uptempo Hardcore", proposal.evidence[0])
        self.assertIn('also possible: Uplifting Trance + Terror', proposal.evidence[1])

    def test_a_blend_prefers_the_popular_genre(self):
        fresh = GenreNameAnalyzer(
            build_dictionary([('Uplifting Trance', 5000), ('Uptempo Hardcore', 5), ('Terror', 1)], [])
        )
        self.assertEqual(fresh.propose('Upterror').values, ['Uplifting Trance', 'Terror'])

    def test_two_fragments_only_blend_when_both_are_long_enough(self):
        proposal = self.propose('Frenchtempo')
        self.assertEqual(
            (proposal.kind, proposal.values, proposal.confidence), (SPLIT, ['Frenchcore', 'Uptempo Hardcore'], 55)
        )
        self.assertNotEqual(self.propose('Shitempo').kind, SPLIT)

    def test_glued_genres_are_cut_apart(self):
        proposal = self.propose('Jungleterror')
        self.assertEqual((proposal.kind, proposal.values, proposal.confidence), (SPLIT, ['Jungle', 'Terror'], 80))

    def test_a_glued_name_prefers_the_longest_known_piece(self):
        self.assertEqual(self.propose('Hardcoretechno').values, ['Hardcore Techno'])

    def test_space_separated_known_genres_split(self):
        proposal = self.propose('Hardcore Early Hardcore')
        self.assertEqual(
            (proposal.kind, proposal.values, proposal.confidence), (SPLIT, ['Hardcore', 'Early Hardcore'], 85)
        )

    def test_fewest_phrases_wins_so_a_two_word_genre_stays_whole(self):
        proposal = self.propose('Hard Techno Terror')
        self.assertEqual(proposal.values, ['Hard Techno', 'Terror'])

    def test_a_misspelt_word_inside_a_list_is_still_recognised(self):
        proposal = self.propose('Industial Hardcore Terror')
        self.assertEqual(proposal.values, ['Industrial Hardcore', 'Terror'])
        self.assertTrue(any('looks like' in line for line in proposal.evidence))

    def test_a_learned_modifier_is_dropped_with_the_lesson_shown(self):
        """`Vocal Trance` -> `Trance` taught that `vocal` is dropped."""
        proposal = self.propose('Vocal Hardcore')
        self.assertEqual((proposal.kind, proposal.values, proposal.confidence), (REWRITE, ['Hardcore'], 70))
        self.assertTrue(any("'vocal' was dropped before" in line for line in proposal.evidence))

    def test_an_unknown_modifier_is_dropped_with_lower_confidence(self):
        proposal = self.propose('Dutch Hardcore')
        self.assertEqual((proposal.kind, proposal.values, proposal.confidence), (REWRITE, ['Hardcore'], 60))
        self.assertIn('dropped: dutch', proposal.evidence[-1])

    def test_a_genre_like_leftover_blocks_the_advice(self):
        proposal = self.propose('Melodic Trance')
        self.assertEqual(proposal.kind, UNKNOWN)
        self.assertIn("'melodic' reads as a genre too", proposal.evidence[0])

    def test_noise_around_a_genre_is_stripped(self):
        self.assertEqual(self.propose('Happy Hardcore Classics').values, ['Happy Hardcore'])
        self.assertEqual(self.propose('Hardcore 2018').values, ['Hardcore'])
        self.assertEqual(self.propose('Add "uptempo"').values, ['Uptempo Hardcore'])
        self.assertEqual(self.propose("'Hardstyle' Toevoegen").values, ['Hardstyle'])
        self.assertEqual(self.propose('Hardstyle Mainstage').confidence, 85)

    def test_a_misspelling_is_a_rewrite_to_the_close_approved_name(self):
        proposal = self.propose('Harddcore')
        self.assertEqual((proposal.kind, proposal.values), (REWRITE, ['Hardcore']))
        self.assertGreaterEqual(proposal.confidence, 90)

    def test_a_misspelling_of_a_corrected_name_lands_on_its_target(self):
        proposal = self.propose('Gym Hardstyel')
        self.assertEqual((proposal.kind, proposal.values), (REWRITE, ['Hardstyle']))

    def test_a_year_glued_to_the_genre_is_still_noise(self):
        proposal = self.propose('Hardstyle2000')
        self.assertEqual((proposal.kind, proposal.values), (REWRITE, ['Hardstyle']))

    def test_a_short_word_one_letter_away_is_worth_less(self):
        proposal = self.propose('Mental')
        self.assertEqual((proposal.kind, proposal.values), (REWRITE, ['Metal']))
        self.assertLess(proposal.confidence, 85)

    def test_an_ampersand_reads_as_the_letter_n(self):
        fresh = GenreNameAnalyzer(build_dictionary([("Drum 'N Bass", 10)], [('Dnb', "Drum 'N Bass")]))
        self.assertEqual(fresh.propose('D&B').values, ["Drum 'N Bass"])

    def test_an_artist_is_rejected_with_a_pointer_to_the_tagger_page(self):
        proposal = self.propose('henry fong')
        self.assertEqual((proposal.kind, proposal.confidence), (REJECT, 85))
        self.assertIn('is an artist, not a genre', proposal.evidence[0])

    def test_an_artist_linked_to_a_genre_becomes_that_genre(self):
        proposal = self.propose('dr peacock')
        self.assertEqual((proposal.kind, proposal.values, proposal.confidence), (REWRITE, ['Frenchcore'], 90))

    def test_a_label_linked_to_a_genre_becomes_that_genre(self):
        self.assertEqual(self.propose('Snakepit Music').values, ['Uptempo Hardcore'])
        self.assertEqual(self.propose('Scarred Digital').kind, REJECT)

    def test_an_artist_that_reads_as_a_genre_is_only_a_footnote(self):
        """`Melodic` is in the artist list, and also a word in `Melodic House`."""
        proposal = self.propose('Melodic')
        self.assertEqual(proposal.kind, UNKNOWN)
        self.assertIn("'Melodic' is also an artist", proposal.evidence[-1])

    def test_label_and_promo_words_reject(self):
        self.assertEqual(self.propose('Partyraiser Recordings').kind, REJECT)
        self.assertEqual(self.propose('Sample Pack Demo').kind, REJECT)
        self.assertIn("'weekly'", self.propose('weekly').evidence[0])

    def test_a_name_close_to_a_rejected_one_is_rejected(self):
        proposal = self.propose('Heartbreaker')
        self.assertEqual((proposal.kind, proposal.confidence), (REJECT, 75))
        self.assertIn("looks like 'HEARTBREAK'", proposal.evidence[0])

    def test_what_resembles_no_genre_at_all_is_proposed_for_rejection(self):
        """`Tafelpoot` is the maintainer's example of a non-genre."""
        proposal = self.propose('Tafelpoot')
        self.assertEqual((proposal.kind, proposal.confidence), (REJECT, 50))
        self.assertEqual(self.propose('Summer').kind, REJECT)

    def test_what_reads_as_a_genre_but_matches_nothing_is_left_to_the_human(self):
        for name in ('Energycore', 'Hardpsy', 'Piepcore', 'Melodic Terror'):
            self.assertEqual(self.propose(name).kind, UNKNOWN, name)

    def test_too_short_empty_and_letterless_names_are_rejected(self):
        self.assertEqual(self.propose('we').evidence, ['too short to be a genre'])
        self.assertEqual(self.propose('   ').confidence, 100)
        self.assertEqual(self.propose('2026').evidence, ['contains no letters'])


class ConfigTest(unittest.TestCase):
    def test_unknown_keys_are_ignored_and_known_ones_applied(self):
        config = GenreAnalyzerConfig.from_dict({'fuzzy_rewrite_threshold': 0.99, 'bogus': 1})
        self.assertEqual(config.fuzzy_rewrite_threshold, 0.99)

    def test_a_stricter_threshold_turns_a_rewrite_into_a_queue_entry(self):
        strict = analyzer(fuzzy_rewrite_threshold=0.99, token_fuzzy_threshold=0.99)
        self.assertNotEqual(strict.propose('Harddcore').kind, REWRITE)

    def test_an_empty_dictionary_still_answers(self):
        empty = GenreNameAnalyzer(GenreDictionary())
        self.assertEqual(empty.propose('Tafelpoot').kind, REJECT)
        self.assertEqual(empty.propose('Hardcore/Terror').kind, UNKNOWN)


if __name__ == '__main__':
    unittest.main()
