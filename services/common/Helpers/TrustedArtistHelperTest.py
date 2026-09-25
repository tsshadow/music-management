"""TrustedArtistHelper: the tagger's artist dictionary is the trusted set, not library_artists."""

import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers.TableHelper import TableHelper
from services.common.Helpers.TrustedArtistHelper import PROMPT_DECIDER, TRUSTED_ARTISTS_SQL, TrustedArtistHelper


class TrustedArtistHelperTest(unittest.TestCase):
    def setUp(self):
        patcher = patch('services.common.Helpers.TableHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        connector_cls = patcher.start()
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        connector_cls.return_value.connect.return_value = self.connection

    def helper(self, rows):
        self.cursor.fetchall.return_value = [(name, rank) for rank, name in enumerate(rows)]
        return TrustedArtistHelper()

    def test_it_loads_the_trusted_query_and_nothing_else(self):
        helper = self.helper(['Angerfist'])
        self.cursor.execute.assert_called_once_with(TRUSTED_ARTISTS_SQL)
        self.assertTrue(helper.exists('angerfist'))
        self.assertFalse(helper.exists('Tagger Guess'))

    def test_the_query_trusts_approval_and_grandfathering_only(self):
        sql = ' '.join(TRUSTED_ARTISTS_SQL.split())
        self.assertIn("r.state = 'white'", sql)
        self.assertIn('JOIN rules_artist_legacy_trust l ON l.name = a.name', sql)
        # A grandfathered name loses its trust the moment anyone decides on it.
        self.assertIn('WHERE r.name IS NULL', sql)
        self.assertNotIn('black', sql)

    def test_the_last_spelling_per_name_wins_so_the_approved_one_does(self):
        helper = self.helper(['ANGERFIST', 'Angerfist'])
        self.assertEqual(helper.get('angerfist'), 'Angerfist')
        self.assertEqual(helper.lowercase_map(), {'angerfist': 'Angerfist'})

    def test_it_is_a_caching_table_helper_even_without_a_preload(self):
        """The rules follow `lowercase_map` identity only for a caching TableHelper, and the
        uncached paths would read library_artists -- the untrusted set -- directly."""
        helper = TrustedArtistHelper(preload=False)
        self.assertIsInstance(helper, TableHelper)
        self.assertTrue(helper.cache_enabled)
        self.cursor.execute.assert_not_called()

    def test_a_failed_reload_keeps_the_previous_snapshot(self):
        helper = self.helper(['Angerfist'])
        self.cursor.execute.side_effect = Exception('database down')
        helper.reload()
        self.assertTrue(helper.exists('Angerfist'))

    def test_the_prompt_approval_is_recorded_as_a_decision(self):
        helper = self.helper([])
        self.cursor.execute.reset_mock()
        self.assertTrue(helper.add('Radical Redemption'))
        statements = [call.args for call in self.cursor.execute.call_args_list]
        self.assertTrue(statements[0][0].startswith('INSERT IGNORE INTO library_artists'))
        self.assertTrue(statements[1][0].startswith('INSERT INTO rules_artists'))
        self.assertEqual(statements[1][1], ('Radical Redemption', 'white', PROMPT_DECIDER))
        self.connection.commit.assert_called_once()
        self.assertTrue(helper.exists('radical redemption'))

    def test_a_failed_prompt_approval_is_not_trusted(self):
        helper = self.helper([])
        self.cursor.execute.side_effect = Exception('insert error')
        self.assertFalse(helper.add('Radical Redemption'))
        self.connection.rollback.assert_called_once()
        self.assertFalse(helper.exists('Radical Redemption'))


if __name__ == '__main__':
    unittest.main()
