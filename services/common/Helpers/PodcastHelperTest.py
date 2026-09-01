import unittest

from services.common.Helpers.PodcastHelper import (
    PodcastHelper,
    Show,
    normalize,
    strip_episode_and_guest,
)


class PodcastHelperGetTest(unittest.TestCase):
    """Matching a curated show against a title or a path."""

    def helper(self, shows):
        """A helper with its lookup pre-filled, so no database is involved."""
        instance = PodcastHelper(preload=False)
        instance.set_shows([Show(name=name, aliases=aliases) for name, aliases in shows.items()])
        return instance

    def test_returns_none_without_a_match(self):
        helper = self.helper({"Hard With Style": ["Hard With Style"]})

        self.assertIsNone(helper.get("Angerfist - Raise Your Fist"))

    def test_matches_an_alias_and_reports_the_canonical_name(self):
        helper = self.helper({"Isaac's Hardstyle Sessions": ["Isaac's Hardstyle Sessions", "Hardstyle Sessions"]})

        result = helper.get("DJ ISAAC - HARDSTYLE SESSIONS #150 | FEBRUARY 2022")

        self.assertEqual("Isaac's Hardstyle Sessions", result["podcast"])
        self.assertEqual("150", result["episode"])

    def test_the_longest_alias_wins(self):
        """A subseries must not be swallowed by the shorter show name it contains."""
        helper = self.helper(
            {
                "Isaac's Hardstyle Sessions": ["Hardstyle Sessions"],
                "Isaac's Hardstyle Sessions Yearmix": ["Hardstyle Sessions Yearmix"],
            }
        )

        result = helper.get("Isaac's Hardstyle Sessions Yearmix #136")

        self.assertEqual("Isaac's Hardstyle Sessions Yearmix", result["podcast"])

    def test_matches_case_and_punctuation_insensitively(self):
        helper = self.helper({"The Uptempo Tribe Podcast": ["The Uptempo Tribe Podcast"]})

        result = helper.get("the·uptempo/tribe podcast #44 - Deviation")

        self.assertEqual("The Uptempo Tribe Podcast", result["podcast"])
        self.assertEqual("44", result["episode"])

    def test_episode_is_none_when_the_title_carries_no_number(self):
        helper = self.helper({"Q-dance Radio": ["Q-dance Radio"]})

        result = helper.get("Q-dance Radio | Hardstyle Top 40 of May 2019")

        self.assertEqual("Q-dance Radio", result["podcast"])
        self.assertIsNone(result["episode"])

    def test_reads_the_show_from_a_path_when_the_filename_omits_it(self):
        helper = self.helper({"The Magic Show": ["The Magic Show"]})

        result = helper.get("/mnt/music/Podcasts/The Magic Show/2011/Podcast week 023.mp3")

        self.assertEqual("The Magic Show", result["podcast"])
        self.assertEqual("023", result["episode"])

    def test_reads_every_supported_episode_marker(self):
        helper = self.helper({"Louder": ["Louder"]})
        cases = {
            "Louder #40": "40",
            "Louder episode 40": "40",
            "Louder Episode #40": "40",
            "Louder ep. 40": "40",
            "Louder podcast 40": "40",
            "Louder week 040": "040",
            "Louder afl 40": "40",
        }

        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(expected, helper.get(title)["episode"])

    def test_an_alias_only_matches_on_word_boundaries(self):
        """'Louder' is a show; 'Loudness' is not an episode of it."""
        helper = self.helper({"Louder": ["Louder"]})

        self.assertIsNone(helper.get("Angerfist - Loudness #3"))
        self.assertIsNotNone(helper.get("The Prophet - Louder #3"))

    def test_matches_before_any_show_is_loaded(self):
        helper = PodcastHelper(preload=False)

        self.assertIsNone(helper.get("Hardstyle Sessions #150"))

    def test_ignores_a_year_that_is_not_an_episode_number(self):
        helper = self.helper({"Louder": ["Louder"]})

        self.assertIsNone(helper.get("The Prophet - Louder 2019 yearmix")["episode"])


class StripEpisodeAndGuestTest(unittest.TestCase):
    """The grouping key the detector builds; the tag rule does not use this."""

    def test_removes_the_episode_marker(self):
        self.assertEqual("hardstyle sessions", strip_episode_and_guest("Hardstyle Sessions #150"))

    def test_removes_a_trailing_guest(self):
        self.assertEqual(
            "official masters of hardcore", strip_episode_and_guest("Official Masters of Hardcore #204 by Korsakoff")
        )

    def test_collapses_guest_variants_onto_one_key(self):
        keys = {
            strip_episode_and_guest("Hardcore Italia #151 mixed by Art of Fighters"),
            strip_episode_and_guest("Hardcore Italia #147 mixed by Meccano Twins"),
            strip_episode_and_guest("Hardcore Italia - Episode 140 - hosted by Nico & Tetta"),
        }

        self.assertEqual({"hardcore italia"}, keys)

    def test_keeps_podcast_when_it_is_part_of_the_show_name(self):
        """'The Uptempo Tribe Podcast' is the name; 'Episode' never is."""
        self.assertEqual(
            "the uptempo tribe podcast", strip_episode_and_guest("The Uptempo Tribe Podcast #44 - Deviation")
        )
        self.assertEqual("monstercat podcast", strip_episode_and_guest("Monstercat Podcast 151"))

    def test_reads_a_scene_release_joined_with_underscores(self):
        self.assertEqual(
            "angerfist twisted darkside podcast",
            strip_episode_and_guest("Angerfist-Twisted_Darkside_Podcast_130-WEB-04-30-2013-CiN_INT"),
        )

    def test_removes_a_month_and_year(self):
        self.assertEqual(
            "isaac s hardstyle sessions", strip_episode_and_guest("ISAAC'S HARDSTYLE SESSIONS #129 | MAY 2020")
        )

    def test_keeps_a_name_that_carries_no_episode_marker_intact(self):
        self.assertEqual("nitrogenetics inside your head", strip_episode_and_guest("Nitrogenetics - Inside Your Head"))


class NormalizeTest(unittest.TestCase):
    def test_matches_the_genre_normalizer(self):
        self.assertEqual("hard with style", normalize("Härd  With—Style!"))

    def test_handles_none(self):
        self.assertEqual("", normalize(None))
