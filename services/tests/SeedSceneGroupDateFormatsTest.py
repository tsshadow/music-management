"""Covers scripts/seed_scene_group_date_formats.py.

The seeding decides, per scene group, whether its NFO dates contradict the positional default. A
wrong verdict here silently misdates every release by that group, so each branch is pinned.
"""

import importlib.util
from collections import Counter
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'seed_scene_group_date_formats.py'

spec = importlib.util.spec_from_file_location('seed_scene_group_date_formats', SCRIPT)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def test_a_day_above_twelve_first_is_day_month():
    assert seed.classify_token('17.10.2025') == 'dm'


def test_a_day_above_twelve_second_is_month_day():
    assert seed.classify_token('02.29.2024') == 'md'


def test_a_year_first_token_is_measured_on_its_two_tail_components():
    assert seed.classify_token('2026.01.25') == 'md'


def test_an_ambiguous_token_is_untestable():
    assert seed.classify_token('05.06.2026') is None


def test_a_token_without_a_year_is_untestable():
    assert seed.classify_token('05.06.26') is None


def test_a_group_that_only_contradicts_the_default_gets_an_override():
    assert seed.group_verdicts({'SPiDeR': Counter({'contradicts': 10})}) == {'SPiDeR': 'md'}


def test_a_group_matching_the_default_gets_no_entry():
    assert seed.group_verdicts({'ZzZz': Counter({'agrees': 231})}) == {}


def test_mixed_evidence_is_left_to_the_default():
    """Encoding a mixture as one order would be a false certainty."""
    assert seed.group_verdicts({'(none)': Counter({'agrees': 13, 'contradicts': 1})}) == {}


def test_a_group_with_no_testable_evidence_gets_no_entry():
    assert seed.group_verdicts({'FMC': Counter()}) == {}


def test_a_single_contradicting_token_is_not_a_format():
    """Twelve groups in the real library had exactly one, which is one odd NFO rather than a format."""
    assert seed.group_verdicts({'LEV': Counter({'contradicts': 1})}) == {}


def test_one_stray_agreement_does_not_save_the_default():
    """Group BC contradicts 170 times and agrees once; that token must not misdate all 170."""
    assert seed.group_verdicts({'BC': Counter({'contradicts': 170, 'agrees': 1})}) == {'BC': 'md'}


def test_noise_in_a_compliant_group_is_ignored():
    """FMC agrees 4922 times and contradicts 3: the three are noise, not a format."""
    assert seed.group_verdicts({'FMC': Counter({'agrees': 4922, 'contradicts': 3})}) == {}


def test_a_genuinely_split_group_is_left_to_the_default():
    """Two against one is not a majority worth acting on."""
    assert seed.group_verdicts({'UTE': Counter({'contradicts': 2, 'agrees': 1})}) == {}
