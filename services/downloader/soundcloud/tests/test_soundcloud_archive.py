import unittest
from unittest.mock import MagicMock, patch

from services.downloader.soundcloud.SoundcloudArchive import SoundcloudArchive
from services.tests.connector_fakes import wire_connector

TRACK = {
    'account_name': 'Angerfist',
    'account_id': '12345',
    'video_id': 'track-1',
    'path': '/music/angerfist/track-1.mp3',
    'url': 'https://soundcloud.com/angerfist/track-1',
    'title': 'Raise Your Fist',
}


class SoundcloudArchiveTestCase(unittest.TestCase):

    def setUp(self):
        patcher = patch('services.downloader.soundcloud.SoundcloudArchive.DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.connector_cls = patcher.start()
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        wire_connector(self.connector_cls.return_value, self.connection)


class TrackExistsTest(SoundcloudArchiveTestCase):
    """The probe's gate: is this track held, regardless of which account it is under?"""

    def test_a_known_track_is_reported_as_archived(self):
        self.cursor.fetchone.return_value = (1,)

        self.assertTrue(SoundcloudArchive.track_exists('2379459947'))

    def test_an_unknown_track_is_not_archived(self):
        self.cursor.fetchone.return_value = None

        self.assertFalse(SoundcloudArchive.track_exists('2379459947'))

    def test_it_matches_on_the_track_id_alone(self):
        # The account column holds the numeric SoundCloud id, not the name the
        # sweep iterates, so filtering on it would never match.
        self.cursor.fetchone.return_value = (1,)

        SoundcloudArchive.track_exists('2379459947')

        query, params = self.cursor.execute.call_args[0]
        self.assertNotIn('account', query)
        self.assertEqual(params, ('2379459947',))

    def test_an_unreachable_database_means_do_the_full_run(self):
        self.connector_cls.return_value.connection.side_effect = RuntimeError('no database')

        self.assertFalse(SoundcloudArchive.track_exists('2379459947'))


class ExistsTest(SoundcloudArchiveTestCase):

    def test_a_known_track_is_reported_as_archived(self):
        self.cursor.fetchone.return_value = (1,)

        self.assertTrue(SoundcloudArchive.exists('Angerfist', 'track-1'))
        self.assertEqual(self.cursor.execute.call_args[0][1], ('Angerfist', 'track-1'))

    def test_an_unknown_track_is_not_archived(self):
        self.cursor.fetchone.return_value = None

        self.assertFalse(SoundcloudArchive.exists('Angerfist', 'track-1'))

    def test_a_database_failure_reads_as_not_archived(self):
        self.cursor.execute.side_effect = Exception('DB Error')

        self.assertFalse(SoundcloudArchive.exists('Angerfist', 'track-1'))


class UploaderIdTest(unittest.TestCase):

    def test_the_channel_id_is_preferred(self):
        self.assertEqual(
            SoundcloudArchive._get_uploader_id({'channel_id': 'c1', 'uploader_id': 'u1'}), 'c1'
        )

    def test_the_uploader_id_is_the_fallback(self):
        self.assertEqual(SoundcloudArchive._get_uploader_id({'uploader_id': 'u1'}), 'u1')

    def test_neither_yields_nothing(self):
        self.assertIsNone(SoundcloudArchive._get_uploader_id({}))


class InsertTest(SoundcloudArchiveTestCase):

    def archive_insert(self):
        for sql, params in (args[0] for args in self.cursor.execute.call_args_list):
            if 'INSERT IGNORE INTO downloads_soundcloud_archive' in sql:
                return params
        return None

    def test_a_new_account_is_registered_alongside_the_track(self):
        self.cursor.fetchone.return_value = None

        SoundcloudArchive.insert(TRACK)

        statements = ' '.join(args[0][0] for args in self.cursor.execute.call_args_list)
        self.assertIn('INSERT IGNORE INTO downloads_soundcloud_accounts', statements)
        self.assertEqual(self.archive_insert(), ('12345', 'track-1', TRACK['path'], TRACK['url'], TRACK['title']))
        self.connection.commit.assert_called_once()

    def test_a_known_account_missing_its_id_is_backfilled(self):
        self.cursor.fetchone.return_value = (None,)

        SoundcloudArchive.insert(TRACK)

        updates = [
            args[0] for args in self.cursor.execute.call_args_list
            if 'UPDATE downloads_soundcloud_accounts' in args[0][0]
        ]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][1], ('12345', 'Angerfist'))

    def test_a_complete_account_is_left_alone(self):
        self.cursor.fetchone.return_value = ('12345',)

        SoundcloudArchive.insert(TRACK)

        statements = ' '.join(args[0][0] for args in self.cursor.execute.call_args_list)
        self.assertNotIn('UPDATE downloads_soundcloud_accounts', statements)
        self.assertNotIn('INSERT IGNORE INTO downloads_soundcloud_accounts', statements)
        self.assertIsNotNone(self.archive_insert())

    def test_a_track_without_an_account_name_is_not_archived(self):
        SoundcloudArchive.insert({**TRACK, 'account_name': None})

        self.cursor.execute.assert_not_called()

    def test_a_track_without_an_id_is_not_archived(self):
        SoundcloudArchive.insert({**TRACK, 'video_id': None})

        self.cursor.execute.assert_not_called()

    def test_a_track_without_a_url_is_not_archived(self):
        SoundcloudArchive.insert({**TRACK, 'url': None})

        self.cursor.execute.assert_not_called()

    def test_a_database_failure_is_swallowed(self):
        self.cursor.execute.side_effect = Exception('DB Error')

        SoundcloudArchive.insert(TRACK)

        self.connection.commit.assert_not_called()


class HeldIdsTest(SoundcloudArchiveTestCase):
    """The deep pass's gate: which of a whole listing do we already hold?"""

    def test_it_returns_the_ids_the_archive_knows(self):
        self.cursor.fetchall.return_value = [('2',)]

        self.assertEqual({'2'}, SoundcloudArchive.held_ids(['1', '2', '3']))

    def test_it_asks_about_every_id_in_one_statement(self):
        self.cursor.fetchall.return_value = []

        SoundcloudArchive.held_ids(['1', '2', '3'])

        self.assertEqual(1, self.cursor.execute.call_count)
        query, params = self.cursor.execute.call_args[0]
        self.assertIn('IN (%s, %s, %s)', query)
        self.assertEqual(('1', '2', '3'), params)

    def test_it_matches_on_the_track_id_alone(self):
        self.cursor.fetchall.return_value = []

        SoundcloudArchive.held_ids(['1'])

        query, _ = self.cursor.execute.call_args[0]
        self.assertNotIn('account', query)

    def test_an_empty_listing_asks_nothing(self):
        self.assertEqual(set(), SoundcloudArchive.held_ids([]))
        self.cursor.execute.assert_not_called()

    def test_a_long_listing_is_split_into_blocks(self):
        self.cursor.fetchall.return_value = []

        SoundcloudArchive.held_ids([str(n) for n in range(1200)])

        self.assertEqual(3, self.cursor.execute.call_count)

    def test_numeric_ids_are_compared_as_strings(self):
        self.cursor.fetchall.return_value = [(2379459947,)]

        self.assertEqual({'2379459947'}, SoundcloudArchive.held_ids([2379459947]))

    def test_a_database_error_is_raised_rather_than_read_as_nothing_held(self):
        # Answering "nothing is held" would turn one broken query into a
        # re-download of the whole account.
        self.cursor.execute.side_effect = RuntimeError('database is down')

        with self.assertRaises(RuntimeError):
            SoundcloudArchive.held_ids(['1'])


if __name__ == '__main__':
    unittest.main()
