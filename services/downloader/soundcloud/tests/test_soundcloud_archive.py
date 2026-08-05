import unittest
from unittest.mock import MagicMock, patch

from services.downloader.soundcloud.SoundcloudArchive import SoundcloudArchive

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
        self.connector_cls.return_value.connect.return_value = self.connection


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


if __name__ == '__main__':
    unittest.main()
