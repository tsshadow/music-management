"""Tests for the judgement in the external-evidence approver.

The HTTP clients are not tested -- they are three URL builders over a cached GET --
but the normalisation and the three approval rules are, on titles from the real
queue, because those decide which names get approved without a human looking.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tools.artist_auto_approve import (  # noqa: E402
    APPROVE,
    DEEZER,
    ITUNES,
    MUSICBRAINZ,
    SKIPPED,
    UNRESOLVED,
    ExternalArtist,
    Fetcher,
    looks_like_a_set,
    normalise_artist,
    normalise_title,
    open_state,
    score_artist,
    usable_titles,
)


class NormaliseTitleTest(unittest.TestCase):
    def test_mix_suffixes_and_promo_tails_go(self):
        cases = {
            'Feel The Electricity (Original Mix)': 'feel the electricity',
            'We Unite (Archive 2024 Anthem) (Extended Mix)': 'we unite',
            'Cobra 6 (Official BKJN vs. Partyraiser 2026 Anthem) (Edit)': 'cobra 6',
            'Holdin´On(Code Crime Bootleg) FREE DOWNLOAD': 'holdin on',
            'Promise You This (Official Video) - Napalm Records': 'promise you this',
            'Extreme Terror (Chaotic Hostility Remix DJ Edit)hardtunes only': 'extreme terror',
            'Stand Up (Milo & Otis Remix) [OUT NOW ON OWSLA!]': 'stand up',
        }
        for raw, expected in cases.items():
            self.assertEqual(normalise_title(raw), expected, raw)

    def test_catalogue_ids_and_labels_go(self):
        self.assertEqual(normalise_title('[DOG021] Ignite'), 'ignite')
        self.assertEqual(normalise_title('PRIMAL CARNAGE [HF01]'), 'primal carnage')
        self.assertEqual(normalise_title('Bitch Mode [ FR002 ]'), 'bitch mode')
        self.assertEqual(normalise_title('Haunted [Silk Music]'), 'haunted')

    def test_a_feature_is_not_part_of_the_song(self):
        self.assertEqual(normalise_title('Symphony feat. Layna (GLD Remix)'), 'symphony')

    def test_unknown_brackets_stay(self):
        self.assertEqual(normalise_title('Chichovite (Reloaded)'), 'chichovite reloaded')

    def test_accents_and_ampersands_fold(self):
        self.assertEqual(normalise_artist('Milo & Otis'), 'milo and otis')
        self.assertEqual(normalise_artist('Dr. Peacock'), normalise_artist('Dr.Peacock'))
        self.assertEqual(normalise_artist('Beyoncé'), 'beyonce')


class SetDetectionTest(unittest.TestCase):
    def test_festival_strings_are_sets(self):
        self.assertTrue(looks_like_a_set('Defqon.1 | ORANGE | Friday'))
        self.assertTrue(looks_like_a_set('Q-dance presents: Scantraxx 15 Years | Chapter 3 Mix'))
        self.assertTrue(looks_like_a_set('Andhim Super-House DJ Set Live From DJ Mag HQ'))

    def test_a_year_inside_the_packaging_does_not_make_a_set(self):
        self.assertFalse(looks_like_a_set('Cobra 6 (Official BKJN vs. Partyraiser 2026 Anthem) (Edit)'))

    def test_usable_titles_drop_sets_and_stubs(self):
        titles = ['180', 'Hatred', 'Defqon.1 | ORANGE | Friday', 'Hatred (Extended Mix)']
        self.assertEqual(usable_titles(titles), {'hatred': 'Hatred'})


def act(source, titles, external_id='1', kind='Person', name='X'):
    return ExternalArtist(source, external_id, name, kind=kind, titles=list(titles))


class ScoreArtistTest(unittest.TestCase):
    local = ['Feel The Electricity (Original Mix)', 'Hardcore War (Edit)', 'Run Mf']

    def test_no_candidates_is_unresolved_not_rejected(self):
        verdict = score_artist('Offensv', self.local, [])
        self.assertEqual(verdict.verdict, UNRESOLVED)

    def test_two_titles_on_one_act_approve(self):
        verdict = score_artist('Offensv', self.local, [act(DEEZER, ['Hardcore War', 'Feel Alive', 'Run Mf'])])
        self.assertEqual((verdict.verdict, verdict.rule), (APPROVE, 'two-titles-one-act'))
        self.assertEqual(sorted(verdict.evidence['matches'][0]['matched']), ['hardcore war', 'run mf'])

    def test_one_title_on_one_act_is_not_enough(self):
        verdict = score_artist('Offensv', self.local, [act(DEEZER, ['Hardcore War'])])
        self.assertEqual(verdict.verdict, UNRESOLVED)

    def test_two_namesakes_with_one_title_each_do_not_pool_into_rule_one(self):
        candidates = [act(ITUNES, ['Run Mf'], '1'), act(ITUNES, ['Cops'], '2')]
        verdict = score_artist('Offensv', self.local + ['COPS'], candidates)
        # Neither title is distinctive, so rule 2 does not rescue it either.
        self.assertEqual(verdict.verdict, UNRESOLVED)

    def test_two_titles_across_sources_approve_when_one_is_distinctive(self):
        candidates = [act(DEEZER, ['Hardcore War']), act(MUSICBRAINZ, ['Feel the Electricity (extended mix)'])]
        verdict = score_artist('Offensv', self.local, candidates)
        self.assertEqual((verdict.verdict, verdict.rule), (APPROVE, 'two-titles-two-sources'))

    def test_one_distinctive_title_needs_musicbrainz_and_a_store(self):
        local = ['Springen Nondeju (Gezellige Uptempo Remix)']
        both = [act(DEEZER, ['Springen Nondeju']), act(MUSICBRAINZ, ['Springen Nondeju'], kind='Group')]
        self.assertEqual(score_artist('Snollebollekes', local, both).rule, 'distinctive-title-two-sources')
        stores_only = [act(DEEZER, ['Springen Nondeju']), act(ITUNES, ['Springen Nondeju'])]
        self.assertEqual(score_artist('Snollebollekes', local, stores_only).verdict, UNRESOLVED)

    def test_a_short_title_is_never_distinctive(self):
        local = ['Cobra 6 (Official Anthem)']
        both = [act(DEEZER, ['Cobra 6']), act(MUSICBRAINZ, ['Cobra 6'])]
        self.assertEqual(score_artist('Skits Vicious', local, both).verdict, UNRESOLVED)

    def test_a_musicbrainz_label_or_event_does_not_count_as_an_act(self):
        candidates = [act(MUSICBRAINZ, ['Hardcore War', 'Run Mf'], kind='Other')]
        self.assertEqual(score_artist('Offensv', self.local, candidates).verdict, UNRESOLVED)
        untyped = [act(MUSICBRAINZ, ['Hardcore War', 'Run Mf'], kind=None)]
        self.assertEqual(score_artist('Offensv', self.local, untyped).verdict, UNRESOLVED)

    def test_brands_are_skipped_whatever_the_evidence(self):
        verdict = score_artist('Q-Dance', ['Ignite', 'Hatred'], [act(DEEZER, ['Ignite', 'Hatred'])])
        self.assertEqual((verdict.verdict, verdict.rule), (SKIPPED, 'brand'))

    def test_a_name_with_only_set_titles_is_skipped(self):
        verdict = score_artist('Naadt', ['Defqon.1 | ORANGE | Friday'], [])
        self.assertEqual((verdict.verdict, verdict.rule), (SKIPPED, 'no-titles'))


class FetcherTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 'state.sqlite')
        self.conn = open_state(self.path)

    def response(self, status, body, headers=None):
        response = MagicMock()
        response.status_code = status
        response.text = body
        response.headers = headers or {}
        return response

    def test_a_deezer_quota_error_is_retried_not_cached_as_an_answer(self):
        fetcher = Fetcher(self.conn)
        fetcher.session = MagicMock()
        fetcher.session.get.side_effect = [
            self.response(200, json.dumps({'error': {'code': 4, 'message': 'Quota limit exceeded'}})),
            self.response(200, json.dumps({'data': [1]})),
        ]
        with patch('tools.artist_auto_approve.time.sleep'):
            self.assertEqual(fetcher.get(DEEZER, 'https://api.deezer.com/x'), {'data': [1]})
        self.assertEqual(fetcher.session.get.call_count, 2)

    def test_a_cached_answer_is_not_fetched_again(self):
        fetcher = Fetcher(self.conn)
        fetcher.session = MagicMock()
        fetcher.session.get.return_value = self.response(200, '{"a": 1}')
        with patch('tools.artist_auto_approve.time.sleep'):
            fetcher.get(ITUNES, 'https://itunes.apple.com/x')
            fetcher.get(ITUNES, 'https://itunes.apple.com/x')
        self.assertEqual(fetcher.session.get.call_count, 1)
        self.assertEqual(Fetcher(self.conn, offline=True).get(ITUNES, 'https://itunes.apple.com/x'), {'a': 1})

    def test_offline_never_touches_the_network(self):
        fetcher = Fetcher(self.conn, offline=True)
        fetcher.session = MagicMock()
        self.assertIsNone(fetcher.get(MUSICBRAINZ, 'https://musicbrainz.org/x'))
        fetcher.session.get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
