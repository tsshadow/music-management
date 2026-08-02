"""Property-based tests for the pure text functions the tagger leans on.

Example-based tests check the cases someone thought of. These state a rule that
has to hold for *any* input and let Hypothesis go looking for the input that
breaks it -- which is what these functions need, because they are fed tens of
thousands of artist and genre strings scraped off SoundCloud and YouTube, full
of unicode, emoji, control characters and things nobody would write by hand.

Two properties that look obvious are deliberately narrowed to ASCII:
normalize() runs NFKD, under which 'ß'.upper() is 'SS' and a single character
can decompose into several. Both are Unicode behaving correctly, not defects,
so the invariants are stated where they actually hold.
"""
import pytest

hypothesis = pytest.importorskip('hypothesis', reason='pip install -r requirements-dev.txt')
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from services.common.Helpers.ArtistNameAnalyzer import (
    KEEP,
    REJECT,
    REWRITE,
    SPLIT,
    UNKNOWN,
    ArtistNameAnalyzer,
    has_letters,
    normalize,
)
from services.common.Helpers.GenreRulesHelper import BLACK, WHITE, GenreRulesHelper
from services.common.Helpers.GenreRulesHelper import UNKNOWN as GENRE_UNKNOWN

# Deliberately wide: the real inputs contain zero-width spaces, emoji, RTL marks
# and stray control characters, so the strategy should too.
NAMES = st.text(alphabet=st.characters(blacklist_categories=('Cs',)), max_size=80)
ASCII_NAMES = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=60)
# Strings that normalize away to nothing: no letter or digit in any script.
PUNCTUATION_ONLY = st.text(alphabet=' \t!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~', max_size=20)

SETTINGS = settings(max_examples=200, deadline=None)
KINDS = {KEEP, REWRITE, SPLIT, REJECT, UNKNOWN}


class NormalizePropertyTest:

    @given(NAMES)
    @SETTINGS
    def test_normalizing_is_idempotent(self, name):
        once = normalize(name)
        assert normalize(once) == once

    @given(NAMES)
    @SETTINGS
    def test_the_result_never_has_leading_or_trailing_whitespace(self, name):
        assert normalize(name) == normalize(name).strip()

    @given(NAMES)
    @SETTINGS
    def test_the_result_is_lowercase(self, name):
        result = normalize(name)
        assert result == result.lower()

    @given(NAMES)
    @SETTINGS
    def test_the_only_separator_left_is_a_single_space(self, name):
        result = normalize(name)
        assert '  ' not in result
        assert all(character.isalnum() or character == ' ' for character in result)

    @given(ASCII_NAMES)
    @SETTINGS
    def test_case_alone_never_changes_the_key(self, name):
        assert normalize(name.upper()) == normalize(name.lower())

    @given(ASCII_NAMES, st.sampled_from(['', ' ', '   ', '\t']))
    @SETTINGS
    def test_surrounding_whitespace_never_changes_the_key(self, name, padding):
        assert normalize(f'{padding}{name}{padding}') == normalize(name)

    @given(NAMES)
    @SETTINGS
    def test_normalizing_is_deterministic(self, name):
        assert normalize(name) == normalize(name)


class HasLettersPropertyTest:

    @given(NAMES)
    @SETTINGS
    def test_it_agrees_with_the_definition_in_every_script(self, name):
        assert has_letters(name) == any(character.isalpha() for character in name)

    @given(st.text(alphabet='0123456789 -_.', max_size=40))
    @SETTINGS
    def test_digits_and_punctuation_alone_are_not_letters(self, name):
        assert has_letters(name) is False


class ProposalPropertyTest:
    """propose() must always answer, whatever it is handed."""

    analyzer = ArtistNameAnalyzer(known_artists=['Angerfist', 'Headhunterz', 'Da Tweekaz'])

    @given(NAMES)
    @SETTINGS
    def test_every_input_yields_one_of_the_five_kinds(self, name):
        assert self.analyzer.propose(name).kind in KINDS

    @given(NAMES)
    @SETTINGS
    def test_the_confidence_is_a_percentage(self, name):
        assert 0 <= self.analyzer.propose(name).confidence <= 100

    @given(NAMES)
    @SETTINGS
    def test_a_proposal_always_carries_its_evidence(self, name):
        proposal = self.analyzer.propose(name)
        assert isinstance(proposal.evidence, list)
        assert all(isinstance(reason, str) for reason in proposal.evidence)

    @given(NAMES)
    @SETTINGS
    def test_the_values_are_always_a_list_of_strings(self, name):
        proposal = self.analyzer.propose(name)
        assert isinstance(proposal.values, list)
        assert all(isinstance(value, str) for value in proposal.values)

    @given(NAMES)
    @SETTINGS
    def test_a_rejection_proposes_no_replacement(self, name):
        proposal = self.analyzer.propose(name)
        if proposal.kind == REJECT:
            assert proposal.values == []

    @given(NAMES)
    @SETTINGS
    def test_a_split_proposes_more_than_one_name(self, name):
        proposal = self.analyzer.propose(name)
        if proposal.kind == SPLIT:
            assert len(proposal.values) > 1

    @given(NAMES)
    @SETTINGS
    def test_a_keep_or_rewrite_proposes_exactly_one_name(self, name):
        proposal = self.analyzer.propose(name)
        if proposal.kind in (KEEP, REWRITE):
            assert len(proposal.values) == 1

    @given(NAMES)
    @SETTINGS
    def test_proposing_is_deterministic(self, name):
        first = self.analyzer.propose(name)
        second = self.analyzer.propose(name)
        assert (first.kind, first.values, first.confidence) == (second.kind, second.values, second.confidence)

    @given(st.sampled_from(['Angerfist', 'Headhunterz', 'Da Tweekaz']),
           st.sampled_from(['', ' ', '  ']))
    @SETTINGS
    def test_a_known_artist_with_stray_whitespace_survives(self, artist, padding):
        proposal = self.analyzer.propose(f'{padding}{artist}{padding}')
        assert proposal.kind != REJECT
        assert proposal.values == [artist] or normalize(proposal.values[0]) == normalize(artist)

    @given(NAMES)
    @SETTINGS
    def test_stripping_affixes_never_grows_the_name(self, name):
        assert len(self.analyzer.strip_affixes(name)[0]) <= len(name)

    @given(NAMES)
    @SETTINGS
    def test_the_junk_score_is_a_non_negative_count_with_a_reason_each(self, name):
        score, reasons = self.analyzer.junk_score(name)
        assert score >= 0
        assert isinstance(reasons, list)
        # Every signal that fires adds a reason, so a score always has one.
        assert (score > 0) == bool(reasons)

    @given(ASCII_NAMES)
    @SETTINGS
    def test_a_name_without_whitespace_is_never_segmented_into_nothing(self, name):
        assume(name.strip() and not any(character.isspace() for character in name))
        segments = self.analyzer.segment(name)
        assert segments is None or len(segments) > 1


class GenreNormalizationPropertyTest:

    helper = GenreRulesHelper(preload=False, rows=[])

    @given(NAMES)
    @SETTINGS
    def test_normalizing_a_genre_is_idempotent(self, name):
        once = self.helper.normalize(name)
        assert self.helper.normalize(once) == once

    @given(ASCII_NAMES)
    @SETTINGS
    def test_case_alone_never_changes_a_genre_key(self, name):
        assert self.helper.normalize(name.upper()) == self.helper.normalize(name.lower())

    @given(NAMES)
    @SETTINGS
    def test_splitting_never_returns_an_empty_result(self, name):
        assume(name.strip())
        parts = self.helper.split_composite(name)
        assert parts
        assert all(isinstance(part, str) for part in parts)

    @given(st.lists(st.text(alphabet=st.characters(whitelist_categories=('Ll', 'Lu')),
                            min_size=1, max_size=12),
                    min_size=2, max_size=4))
    @SETTINGS
    def test_a_slash_separated_genre_splits_into_its_parts(self, parts):
        assert self.helper.split_composite('/'.join(parts)) == parts

    @given(NAMES)
    @SETTINGS
    def test_splitting_never_invents_characters(self, name):
        assume(name.strip())
        for part in self.helper.split_composite(name):
            assert part in name or part == name.strip()

    @given(NAMES)
    @SETTINGS
    def test_an_unknown_genre_resolves_to_a_valid_decision(self, name):
        assume(name.strip())
        decision = self.helper.resolve(name)
        assert decision.state in {WHITE, BLACK, GENRE_UNKNOWN}
        assert isinstance(decision.values, list)
        assert all(isinstance(value, str) for value in decision.values)

    @given(NAMES)
    @SETTINGS
    def test_a_genre_no_rule_covers_is_returned_stripped_but_otherwise_intact(self, name):
        """With no rows loaded nothing is decided, so anything that normalizes to
        a non-empty key comes back as the trimmed input."""
        assume(self.helper.normalize(name))
        decision = self.helper.resolve(name)
        assert decision.state == GENRE_UNKNOWN
        assert decision.values == [name.strip()]

    @given(PUNCTUATION_ONLY)
    @SETTINGS
    def test_a_genre_that_is_only_punctuation_is_dropped(self, name):
        """A tag of pure punctuation has no key to index on, so it is blacklisted
        rather than queued for curation -- there is nothing for a human to decide."""
        assume(not self.helper.normalize(name))
        decision = self.helper.resolve(name)
        assert decision.state == BLACK
        assert decision.values == []
