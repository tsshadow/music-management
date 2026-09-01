"""The real examples from the library are the specification here.

Every case in `TestRealWorldExamples` is a name the maintainer pointed at in the
actual artist list, with the outcome they said it should have.
"""

import unittest

from services.common.Helpers.ArtistNameAnalyzer import (
    KEEP,
    REJECT,
    REWRITE,
    SPLIT,
    UNKNOWN,
    AnalyzerConfig,
    ArtistNameAnalyzer,
    normalize,
)

KNOWN = ['Angerfist', 'Headhunterz', 'Terrorclown', 'R3trix', 'DJ KURT', 'Da Tweekaz', 'Warface']


class NormalizeTest(unittest.TestCase):
    def test_casing_and_punctuation_collapse(self):
        self.assertEqual(normalize('DJ  Kurt!'), 'dj kurt')

    def test_accents_are_stripped(self):
        self.assertEqual(normalize('Frenchcöre'), 'frenchcore')

    def test_name_without_alphanumerics_has_no_key(self):
        self.assertEqual(normalize('***'), '')


class TestRealWorldExamples(unittest.TestCase):
    """Names taken verbatim from the maintainer's own artist list."""

    def setUp(self):
        self.analyzer = ArtistNameAnalyzer(KNOWN)

    def test_angerfist_is_correct(self):
        proposal = self.analyzer.propose('Angerfist')
        self.assertEqual(proposal.kind, KEEP)
        self.assertEqual(proposal.values, ['Angerfist'])

    def test_headhunterz_is_correct(self):
        self.assertEqual(self.analyzer.propose('Headhunterz').kind, KEEP)

    def test_quote_tagged_as_artist_is_flagged_for_review(self):
        """Flagged, not removed — shape alone is not enough to delete a name.

        Real artists in the library score exactly like this quote does, so the
        signals are reported and the name goes to the queue. Turning
        `reject_on_junk_score` on makes it a removal.
        """
        proposal = self.analyzer.propose('Als wij samen komen(')
        self.assertEqual(proposal.kind, UNKNOWN)
        self.assertTrue(any('function words' in e for e in proposal.evidence))
        self.assertGreaterEqual(proposal.junk_score, AnalyzerConfig().junk_score_threshold)

    def test_the_same_quote_is_removed_when_configured_to(self):
        aggressive = ArtistNameAnalyzer(KNOWN, AnalyzerConfig(reject_on_junk_score=True))
        self.assertEqual(aggressive.propose('Als wij samen komen(').kind, REJECT)

    def test_numbered_prefix_is_corrected(self):
        proposal = self.analyzer.propose('#1 Terrorclown')
        self.assertEqual(proposal.kind, REWRITE)
        self.assertEqual(proposal.values, ['Terrorclown'])

    def test_leading_ampersand_is_corrected(self):
        proposal = self.analyzer.propose('& R3trix')
        self.assertEqual(proposal.kind, REWRITE)
        self.assertEqual(proposal.values, ['R3trix'])

    def test_free_download_wrapper_is_corrected(self):
        proposal = self.analyzer.propose('**FREE DOWNLOAD** DJ KURT')
        self.assertEqual(proposal.kind, REWRITE)
        self.assertEqual(proposal.values, ['DJ KURT'])

    def test_glued_names_are_split_when_segmentation_is_enabled(self):
        analyzer = ArtistNameAnalyzer(KNOWN, AnalyzerConfig(enable_segmentation=True))
        proposal = analyzer.propose('AngerfistHeadhunter')
        self.assertEqual(proposal.kind, SPLIT)
        self.assertEqual(proposal.values, ['Angerfist', 'Headhunterz'])

    def test_segmentation_is_off_by_default(self):
        """It took `Technotronic` apart into `Techno` + `Tonic` on the real data."""
        self.assertNotEqual(self.analyzer.propose('AngerfistHeadhunter').kind, SPLIT)


class RealArtistsMustSurviveTest(unittest.TestCase):
    """Names the first run over the real library wrongly proposed removing."""

    def setUp(self):
        self.analyzer = ArtistNameAnalyzer(KNOWN)

    def test_cyrillic_artists_are_not_treated_as_letterless(self):
        for name in ['Овсянкин', 'Мой Бумажный Пакет', 'катровасер']:
            self.assertNotEqual(self.analyzer.propose(name).kind, REJECT, name)

    def test_a_cyrillic_name_still_gets_a_lookup_key(self):
        """An empty key would make every Cyrillic artist collide into one."""
        self.assertNotEqual(normalize('Овсянкин'), '')
        self.assertNotEqual(normalize('Овсянкин'), normalize('катровасер'))

    def test_dutch_particles_in_a_name_do_not_remove_it(self):
        self.assertNotEqual(self.analyzer.propose('Boaz Van De Beatz').kind, REJECT)

    def test_english_band_names_do_not_remove_themselves(self):
        for name in ['We Are Loud', 'WE ARE MIR']:
            self.assertNotEqual(self.analyzer.propose(name).kind, REJECT, name)

    def test_an_artist_with_a_bracketed_alias_is_not_removed(self):
        self.assertNotEqual(self.analyzer.propose('The Beholder (Neophyte)').kind, REJECT)

    def test_a_name_that_is_only_noise_is_still_removed(self):
        """The rule that survives: nothing left once the noise is gone."""
        for name in ['Premiere', 'FREE DOWNLOAD', 'OUT NOW']:
            self.assertEqual(self.analyzer.propose(name).kind, REJECT, name)


class ProposalSafetyTest(unittest.TestCase):
    """What the analyzer must refuse to do."""

    def setUp(self):
        self.analyzer = ArtistNameAnalyzer(KNOWN)

    def test_unseen_name_is_unknown_not_rejected(self):
        """An artist can be real and simply absent from the dictionary."""
        proposal = self.analyzer.propose('Obscure Local DJ')
        self.assertEqual(proposal.kind, UNKNOWN)
        self.assertEqual(proposal.values, ['Obscure Local DJ'])

    def test_unknown_keeps_the_name_so_nothing_is_lost(self):
        self.assertEqual(self.analyzer.propose('Zzz Unheard').values, ['Zzz Unheard'])

    def test_name_without_letters_is_rejected(self):
        self.assertEqual(self.analyzer.propose('#12').kind, REJECT)

    def test_empty_name_is_rejected(self):
        self.assertEqual(self.analyzer.propose('   ').kind, REJECT)

    def test_names_with_spaces_are_never_segmented(self):
        """A spaced string needing a split is a delimiter bug, not a glued name."""
        self.assertIsNone(self.analyzer.segment('Angerfist Headhunterz'))

    def test_a_known_artist_is_never_segmented_into_others(self):
        analyzer = ArtistNameAnalyzer(KNOWN + ['War', 'Face'])
        self.assertIsNone(analyzer.segment('Warface'))

    def test_short_fragments_do_not_form_segments(self):
        analyzer = ArtistNameAnalyzer(['Ab', 'Cd'])
        self.assertIsNone(analyzer.segment('AbCd'))

    def test_casing_variant_is_a_rewrite_to_the_approved_spelling(self):
        proposal = self.analyzer.propose('angerfist')
        self.assertEqual(proposal.kind, REWRITE)
        self.assertEqual(proposal.values, ['Angerfist'])

    def test_every_proposal_carries_its_reasoning(self):
        for name in ['Angerfist', '#1 Terrorclown', 'Als wij samen komen(', 'Obscure Local DJ']:
            self.assertTrue(self.analyzer.propose(name).evidence, name)


class AffixStrippingTest(unittest.TestCase):
    def setUp(self):
        self.analyzer = ArtistNameAnalyzer(KNOWN)

    def test_reports_what_it_removed(self):
        stripped, removed = self.analyzer.strip_affixes('**FREE DOWNLOAD** DJ KURT')
        self.assertEqual(stripped, 'DJ KURT')
        self.assertTrue(removed)

    def test_removes_several_layers(self):
        stripped, _ = self.analyzer.strip_affixes('**FREE DOWNLOAD** #1 Terrorclown')
        self.assertEqual(stripped, 'Terrorclown')

    def test_youtube_topic_suffix(self):
        stripped, _ = self.analyzer.strip_affixes('Angerfist - Topic')
        self.assertEqual(stripped, 'Angerfist')

    def test_leaves_a_clean_name_alone(self):
        stripped, removed = self.analyzer.strip_affixes('Da Tweekaz')
        self.assertEqual(stripped, 'Da Tweekaz')
        self.assertEqual(removed, [])


class FuzzyMatchTest(unittest.TestCase):
    def setUp(self):
        self.analyzer = ArtistNameAnalyzer(KNOWN)

    def test_misspelling_is_corrected(self):
        proposal = self.analyzer.propose('Angerfyst')
        self.assertEqual(proposal.kind, REWRITE)
        self.assertEqual(proposal.values, ['Angerfist'])

    def test_single_typo_reaches_down_to_eight_character_names(self):
        """One wrong character scores 1 - 1/n, so the default reaches n = 8."""
        analyzer = ArtistNameAnalyzer(['Ophidian'])
        self.assertEqual(analyzer.propose('Ophidiam').values, ['Ophidian'])

    def test_shorter_names_are_left_to_a_human(self):
        """Below that the same ratio would also match genuinely different names.

        Pins the cost of the default rather than hiding it: a typo in a
        seven-character name is not corrected automatically.
        """
        self.assertEqual(self.analyzer.propose('Warfoce').kind, UNKNOWN)

    def test_a_different_name_is_not_corrected_into_a_known_one(self):
        self.assertEqual(self.analyzer.propose('Radical Redemption').kind, UNKNOWN)


class LengthWindowTest(unittest.TestCase):
    """The index that keeps a 51k-name run from being quadratic."""

    def setUp(self):
        self.analyzer = ArtistNameAnalyzer(KNOWN)

    def test_window_always_contains_the_length_itself(self):
        for length in range(1, 40):
            self.assertIn(length, self.analyzer._length_window(length, 0.87))

    def test_window_narrows_as_the_threshold_rises(self):
        wide = self.analyzer._length_window(20, 0.7)
        narrow = self.analyzer._length_window(20, 0.95)
        self.assertLess(len(narrow), len(wide))

    def test_window_is_empty_for_a_zero_length_key(self):
        self.assertEqual(len(self.analyzer._length_window(0, 0.87)), 0)

    def test_narrowing_never_hides_a_match_propose_would_accept(self):
        """Anything excluded by length could not have cleared the threshold."""
        for name in ['Angerfyst', 'Headhunters', 'Terrorclown', 'Da Tweekas']:
            closest, ratio = self.analyzer.closest_known(name)
            if ratio >= AnalyzerConfig().fuzzy_rewrite_threshold:
                self.assertIsNotNone(closest, name)

    def test_a_typo_in_the_first_character_is_left_to_a_human(self):
        """The cost of first-character blocking, pinned rather than hidden.

        `Sngerfist` is one character off `Angerfist`, but blocking never compares
        them. It lands in the queue instead of being corrected, which is the safe
        direction, and it is what makes a 51k run finish at all.
        """
        self.assertEqual(self.analyzer.propose('Sngerfist').kind, UNKNOWN)

    def test_a_name_unlike_anything_known_has_no_close_match(self):
        closest, ratio = self.analyzer.closest_known('Completely Different Person')
        self.assertLess(ratio, AnalyzerConfig().fuzzy_rewrite_threshold)
        self.assertNotEqual(closest, 'Angerfist')


class ConfigTest(unittest.TestCase):
    def test_thresholds_are_configurable(self):
        strict = ArtistNameAnalyzer(KNOWN, AnalyzerConfig(fuzzy_rewrite_threshold=0.99))
        self.assertEqual(strict.propose('Angerfyst').kind, UNKNOWN)

    def test_junk_threshold_is_configurable(self):
        lenient = ArtistNameAnalyzer(KNOWN, AnalyzerConfig(junk_score_threshold=99))
        self.assertNotEqual(lenient.propose('Als wij samen komen(').kind, REJECT)

    def test_from_dict_ignores_unknown_keys(self):
        config = AnalyzerConfig.from_dict({'junk_score_threshold': 7, 'nonsense': 1})
        self.assertEqual(config.junk_score_threshold, 7)

    def test_from_dict_without_values_returns_defaults(self):
        self.assertEqual(AnalyzerConfig.from_dict(None).junk_score_threshold, AnalyzerConfig().junk_score_threshold)


class DictionaryGrowthTest(unittest.TestCase):
    """Approving one artist has to rescue its polluted variants next pass."""

    def test_variant_is_unknown_until_the_real_name_is_approved(self):
        analyzer = ArtistNameAnalyzer([])
        self.assertEqual(analyzer.propose('**FREE DOWNLOAD** DJ KURT').kind, UNKNOWN)
        analyzer.set_known_artists(['DJ KURT'])
        self.assertEqual(analyzer.propose('**FREE DOWNLOAD** DJ KURT').kind, REWRITE)


if __name__ == '__main__':
    unittest.main()
