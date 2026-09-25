"""Which channels get a link proposal, and to what. See docs/designs/channel-links/technical.md."""

import unittest

from services.music_manager.channel_links import (
    ALIAS,
    ARTIST,
    LABEL,
    NAME,
    REDIRECT,
    Channel,
    artist_index,
    label_index,
    name_key,
    propose_links,
)


def run(channels, labels=(), approved=(), aliases=(), redirects=()):
    """Proposals keyed by (channel id, kind), plus the ambiguous count."""
    result = propose_links(channels, [label_index(labels), artist_index(approved, aliases, redirects)])
    return {(p.channel_id, p.kind): p for p in result.proposals}, result.ambiguous


class NameKeyTest(unittest.TestCase):
    def test_case_accents_punctuation_and_spacing_do_not_matter(self):
        self.assertEqual(name_key('RSLVD Records'), name_key('RSLVD Records †'))
        self.assertEqual(name_key('Dr. Peacock'), name_key('dr  peacock'))
        self.assertEqual(name_key('Beyoncé'), name_key('BEYONCE'))

    def test_letters_outside_ascii_are_kept(self):
        """The ASCII key would drop them and let two different names collapse into one."""
        self.assertNotEqual(name_key('Ħ Angerfist'), name_key('Angerfist'))
        self.assertEqual('vaze', name_key('Ｖａｚｅ'))


class ProposalTest(unittest.TestCase):
    def test_a_channel_equal_to_a_label_gets_a_label_proposal(self):
        proposals, _ = run([Channel(1, 'soundcloud', 'Traxtorm')], labels=[(10, 'Traxtorm')])
        self.assertEqual(
            (10, 'Traxtorm', NAME),
            (proposals[(1, LABEL)].target_id, proposals[(1, LABEL)].target_name, proposals[(1, LABEL)].source),
        )

    def test_a_channel_equal_to_both_gets_one_of_each(self):
        proposals, _ = run(
            [Channel(1, 'youtube', 'Monstercat')], labels=[(10, 'Monstercat')], approved=[(20, 'Monstercat')]
        )
        self.assertEqual({(1, LABEL), (1, ARTIST)}, set(proposals))

    def test_resemblance_is_not_proposed(self):
        proposals, ambiguous = run(
            [Channel(1, 'soundcloud', 'Hysta Official'), Channel(2, 'soundcloud', 'Djkronosofficial')],
            labels=[(10, 'Hysta')],
            approved=[(20, 'Hysta'), (21, 'DJ Kronos')],
        )
        self.assertEqual({}, proposals)
        self.assertEqual(0, ambiguous)

    def test_an_empty_key_matches_nothing(self):
        proposals, _ = run([Channel(1, 'soundcloud', '†††')], labels=[(10, '---')], approved=[(20, '???')])
        self.assertEqual({}, proposals)

    def test_platform_names_and_placeholders_are_no_labels(self):
        proposals, _ = run(
            [Channel(1, 'soundcloud', 'Youtube'), Channel(2, 'soundcloud', '__TODO')],
            labels=[(10, 'Youtube'), (11, '__TODO')],
        )
        self.assertEqual({}, proposals)

    def test_telegram_channels_are_not_considered(self):
        proposals, _ = run([Channel(1, 'telegram', 'Traxtorm')], labels=[(10, 'Traxtorm')])
        self.assertEqual({}, proposals)

    def test_a_kind_already_linked_gets_no_proposal(self):
        proposals, _ = run(
            [Channel(1, 'soundcloud', 'Monstercat', label_id=10)],
            labels=[(10, 'Monstercat')],
            approved=[(20, 'Monstercat')],
        )
        self.assertEqual({(1, ARTIST)}, set(proposals))


class AmbiguityTest(unittest.TestCase):
    def test_the_exact_spelling_wins_among_equal_keys(self):
        proposals, ambiguous = run(
            [Channel(1, 'soundcloud', 'Dr. Peacock')],
            approved=[(20, 'Dr Peacock'), (21, 'dr. peacock'), (22, 'Dr.Peacock')],
        )
        self.assertEqual(21, proposals[(1, ARTIST)].target_id)
        self.assertEqual(0, ambiguous)

    def test_no_exact_spelling_means_no_proposal(self):
        proposals, ambiguous = run(
            [Channel(1, 'soundcloud', 'Dimitri-K')], approved=[(20, 'Dimitri K'), (21, 'Dimitri K.')]
        )
        self.assertEqual({}, proposals)
        self.assertEqual(1, ambiguous)

    def test_two_rows_reaching_one_target_are_one_candidate(self):
        proposals, _ = run(
            [Channel(1, 'soundcloud', 'Air G')], approved=[(20, 'Air G')], aliases=[(20, 'Air G', 'AIR-G')]
        )
        self.assertEqual(20, proposals[(1, ARTIST)].target_id)


class TierTest(unittest.TestCase):
    def test_an_alias_is_consulted_when_no_name_matches(self):
        proposals, _ = run(
            [Channel(1, 'soundcloud', 'Angerfist Official')],
            approved=[(20, 'Angerfist')],
            aliases=[(20, 'Angerfist', 'Angerfist Official')],
        )
        self.assertEqual(
            (20, 'Angerfist', ALIAS),
            (proposals[(1, ARTIST)].target_id, proposals[(1, ARTIST)].target_name, proposals[(1, ARTIST)].source),
        )

    def test_a_redirect_names_the_canonical_artist(self):
        proposals, _ = run(
            [Channel(1, 'soundcloud', 'D - Fence')],
            approved=[(20, 'D-Fence Official')],
            redirects=[(20, 'D-Fence Official', 'D Fence')],
        )
        self.assertEqual((20, REDIRECT), (proposals[(1, ARTIST)].target_id, proposals[(1, ARTIST)].source))

    def test_a_direct_name_beats_an_alias_to_someone_else(self):
        proposals, _ = run(
            [Channel(1, 'soundcloud', 'Darkside')],
            approved=[(20, 'Darkside'), (21, 'Other')],
            aliases=[(21, 'Other', 'Darkside')],
        )
        self.assertEqual((20, NAME), (proposals[(1, ARTIST)].target_id, proposals[(1, ARTIST)].source))

    def test_an_ambiguous_name_tier_does_not_fall_through_to_an_alias(self):
        proposals, ambiguous = run(
            [Channel(1, 'soundcloud', 'S_Dee')],
            approved=[(20, 'S Dee'), (21, 'S-Dee'), (22, 'Third')],
            aliases=[(22, 'Third', 'S_Dee')],
        )
        self.assertEqual({}, proposals)
        self.assertEqual(1, ambiguous)


if __name__ == '__main__':
    unittest.main()
