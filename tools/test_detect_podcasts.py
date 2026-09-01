import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tools.detect_podcasts import EXCLUDED_ROOTS, group_series  # noqa: E402


class GroupSeriesTest(unittest.TestCase):
    def test_reports_each_spelling_of_a_show_as_its_own_candidate(self):
        """
        Three real spellings of Isaac's show stay three candidates.

        Deciding that "DJ ISAAC - HARDSTYLE SESSIONS" is the same show as "Isaac's
        Hardstyle Sessions" is a judgement, so it is a curation merge rather than
        something the detector guesses. What the detector must not do is lose one.
        """
        paths = [
            "/mnt/music/Soundcloud/DJ Isaac/Isaac's Hardstyle Sessions #44 (April 2013).m4a",
            "/mnt/music/Soundcloud/DJ Isaac/Isaac's Hardstyle Sessions #65 (January 2015).m4a",
            '/mnt/music/Youtube/DJ ISAAC/DJ ISAAC - HARDSTYLE SESSIONS #150 | FEBRUARY 2022.m4a',
            '/mnt/music/Youtube/DJ ISAAC/DJ ISAAC - HARDSTYLE SESSIONS #154 | JUNE 2022.m4a',
            "/mnt/music/Youtube/DJ ISAAC/Q-Dance: Isaac's Hardstyle Sessions: Episode #21.m4a",
        ]

        series = group_series(paths, min_episodes=1)

        by_key = {row.key: row.count for row in series}
        self.assertEqual(
            {
                "isaac s hardstyle sessions": 2,
                'dj isaac hardstyle sessions': 2,
                "q dance isaac s hardstyle sessions": 1,
            },
            by_key,
        )

    def test_ignores_files_without_an_episode_marker(self):
        """Detection has to stay conservative: it proposes new rows."""
        paths = [
            '/mnt/music/EPs/Barbaric Records/Manifest Destiny - DMT.mp3',
            '/mnt/music/Soundcloud/Angerfist/Angerfist - Raise Your Fist.mp3',
        ]

        self.assertEqual([], group_series(paths, min_episodes=1))

    def test_skips_label_releases_under_eps(self):
        """'Hard With Style' is a label there, not the radio show."""
        paths = [
            '/mnt/music/EPs/Hard With Style/HWSD003d VA - This Is Hard With Style 1/11 - technoboy - digital nation.mp3',
            '/mnt/music/EPs/Hard With Style/HWSD003d VA - This Is Hard With Style 1/35 - audiofreq - riot.mp3',
        ]

        self.assertEqual([], group_series(paths, min_episodes=1))
        self.assertIn('EPs', EXCLUDED_ROOTS)

    def test_reads_the_series_from_the_folder_when_the_filename_omits_it(self):
        paths = [
            '/mnt/music/Podcasts/The Magic Show/2011/Podcast week 023.mp3',
            '/mnt/music/Podcasts/The Magic Show/2011/Podcast week 024.mp3',
        ]

        series = group_series(paths, min_episodes=1)

        self.assertEqual(1, len(series))
        self.assertEqual('the magic show', series[0].key)
        self.assertEqual(2, series[0].count)

    def test_merges_guest_hosted_episodes_into_one_series(self):
        paths = [
            '/mnt/music/Soundcloud/Masters of Hardcore/Official Masters of Hardcore #204 by Korsakoff.mp3',
            '/mnt/music/Soundcloud/Masters of Hardcore/Official Masters of Hardcore #213 by Negative A.mp3',
            '/mnt/music/Soundcloud/Masters of Hardcore/Official Masters of Hardcore #188 by Tears of Fury.mp3',
        ]

        series = group_series(paths, min_episodes=3)

        self.assertEqual(1, len(series))
        self.assertEqual(3, series[0].count)

    def test_honours_the_minimum_episode_count(self):
        paths = [
            '/mnt/music/Soundcloud/Slam Harder/Slam Harder #1.mp3',
            '/mnt/music/Soundcloud/Slam Harder/Slam Harder #2.mp3',
        ]

        self.assertEqual([], group_series(paths, min_episodes=3))
        self.assertEqual(1, len(group_series(paths, min_episodes=2)))

    def test_reports_a_readable_name_and_the_spellings_behind_it(self):
        paths = [
            '/mnt/music/Soundcloud/Barbaric Records/The Uptempo Tribe Podcast #22 | 2022 Yearmix.mp3',
            '/mnt/music/Soundcloud/Barbaric Records/The Uptempo Tribe Podcast #44 - Deviation.mp3',
            '/mnt/music/Youtube/Barbaric/the uptempo tribe podcast #45.mp3',
        ]

        series = group_series(paths, min_episodes=1)

        self.assertEqual('The Uptempo Tribe Podcast', series[0].name)
        self.assertEqual({'The Uptempo Tribe Podcast', 'the uptempo tribe podcast'}, set(series[0].aliases))

    def test_orders_the_largest_series_first(self):
        paths = [f'/mnt/music/Soundcloud/A/Small Show #{n}.mp3' for n in range(2)]
        paths += [f'/mnt/music/Soundcloud/B/Big Show #{n}.mp3' for n in range(5)]

        series = group_series(paths, min_episodes=1)

        self.assertEqual(['big show', 'small show'], [row.key for row in series])

    def test_ignores_non_audio_files(self):
        paths = [f'/mnt/music/Podcasts/Slam Harder/Slam Harder #{n}.jpg' for n in range(4)]

        self.assertEqual([], group_series(paths, min_episodes=1))


if __name__ == '__main__':
    unittest.main()
