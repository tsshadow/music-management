import unittest
from datetime import datetime, timedelta

from services.music_manager.feeds.profile import build_profile

NOW = datetime(2026, 9, 5, 12, 0, 0)
PARENTS = {'uptempo': {'hardcore'}}
NO_EXCLUSIONS = {'artist': set(), 'label': set(), 'genre': set()}


def listen(
    uid,
    artist='Angerfist',
    labels=('Masters of Hardcore',),
    genres=('Uptempo', 'Hardcore'),
    days=0,
    method='exact',
    played=None,
):
    return {
        'track_uid': uid,
        'listened_at': NOW - timedelta(days=days),
        'match_method': method,
        'played_secs': played,
        'artist': artist,
        'labels': list(labels),
        'genres': list(genres),
    }


class BuildProfileTest(unittest.TestCase):
    def test_the_parent_genre_gets_nothing_from_a_child_tag(self):
        rows = [listen(f'u{i}') for i in range(4)]
        profile = build_profile(rows, PARENTS, NO_EXCLUSIONS, NOW)
        self.assertIn('uptempo', profile.genres)
        self.assertNotIn('hardcore', profile.genres)

    def test_a_plain_parent_listen_still_counts(self):
        rows = [listen(f'u{i}', genres=('Hardcore',)) for i in range(2)]
        profile = build_profile(rows, PARENTS, NO_EXCLUSIONS, NOW)
        self.assertIn('hardcore', profile.genres)

    def test_the_strongest_entity_in_a_dimension_normalises_to_one(self):
        rows = [listen(f'u{i}', artist='Angerfist') for i in range(4)]
        rows += [listen(f'v{i}', artist='Nosferatu') for i in range(2)]
        profile = build_profile(rows, PARENTS, NO_EXCLUSIONS, NOW)
        self.assertAlmostEqual(max(profile.artists.values()), 1.0)
        self.assertLess(profile.artists['nosferatu'], 1.0)

    def test_an_entity_backed_by_one_track_is_dropped(self):
        rows = [listen(f'u{i}', artist='Angerfist') for i in range(3)]
        rows += [listen('lonely', artist='Someone Else')]
        profile = build_profile(rows, PARENTS, NO_EXCLUSIONS, NOW)
        self.assertNotIn('someone else', profile.artists)

    def test_repeating_one_track_cannot_take_over_the_profile(self):
        rows = [listen('same', artist='Looped') for _ in range(50)]
        rows += [listen('same2', artist='Looped')]
        rows += [listen(f'w{i}', artist='Varied') for i in range(4)]
        profile = build_profile(rows, PARENTS, NO_EXCLUSIONS, NOW)
        self.assertLessEqual(profile.artists['looped'], profile.artists['varied'])

    def test_a_track_splits_its_weight_over_its_labels(self):
        rows = [listen(f'u{i}', labels=('A', 'B')) for i in range(3)]
        profile = build_profile(rows, PARENTS, NO_EXCLUSIONS, NOW)
        self.assertAlmostEqual(profile.labels['a'], profile.labels['b'])

    def test_an_excluded_label_contributes_nothing(self):
        rows = [listen(f'u{i}', labels=('Masters of Hardcore',)) for i in range(3)]
        exclusions = {'artist': set(), 'label': {'masters of hardcore'}, 'genre': set()}
        profile = build_profile(rows, PARENTS, exclusions, NOW)
        self.assertEqual(profile.labels, {})

    def test_distinct_tracks_counts_tracks_not_listens(self):
        rows = [listen('same') for _ in range(10)]
        profile = build_profile(rows, PARENTS, NO_EXCLUSIONS, NOW)
        self.assertEqual(profile.distinct_tracks, 1)

    def test_no_listens_yields_an_empty_profile(self):
        profile = build_profile([], PARENTS, NO_EXCLUSIONS, NOW)
        self.assertEqual(profile.scope, 'empty')
        self.assertEqual(profile.genres, {})
