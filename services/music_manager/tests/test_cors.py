"""The origin allowlist."""

import unittest

from services.music_manager.cors import DEFAULT_ORIGINS, allowed_origins


class AllowedOriginsTest(unittest.TestCase):
    def test_an_unset_setting_falls_back_to_the_development_origins(self):
        self.assertEqual(allowed_origins(None), list(DEFAULT_ORIGINS))

    def test_an_empty_setting_is_the_same_as_unset(self):
        self.assertEqual(allowed_origins('   '), list(DEFAULT_ORIGINS))

    def test_a_single_origin_is_used_as_given(self):
        self.assertEqual(allowed_origins('https://muma.example'), ['https://muma.example'])

    def test_several_origins_are_split_and_trimmed(self):
        self.assertEqual(
            allowed_origins('https://a.example , https://b.example'),
            ['https://a.example', 'https://b.example'],
        )

    def test_a_wildcard_still_means_everything(self):
        """The escape hatch: restores the old behaviour without a code change."""
        self.assertEqual(allowed_origins('*'), ['*'])

    def test_a_wildcard_among_others_wins(self):
        self.assertEqual(allowed_origins('https://a.example,*'), ['*'])


if __name__ == '__main__':
    unittest.main()
