import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.music_manager.artist_image_fetcher import fetcher as fetcher_module
from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher


def make_cursor(conn):
    """pymysql cursors are used as context managers; hand back the same mock either way."""
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    return cursor


class FetcherTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(
            os.environ,
            {'ARTIST_IMAGE_STORAGE_PATH': self.tmp.name, 'ARTIST_IMAGE_PUBLIC_BASE_URL': '/media/artist-images'},
        )
        env.start()
        self.addCleanup(env.stop)
        self.conn = MagicMock()
        self.cursor = make_cursor(self.conn)
        self.fetcher = ArtistImageFetcher(db_conn=self.conn)
        self.fetcher.mb_provider = MagicMock()
        self.fetcher.mb_provider.get_artist_metadata.return_value = None
        self.fetcher.providers = []
        self.fetcher.downloader = MagicMock()
        self.fetcher.storage = MagicMock()
        self.fetcher.storage.storage_path = self.tmp.name
        self.fetcher.storage.public_base_url = '/media/artist-images'
        self.fetcher.storage.save_image.return_value = {
            'cached_path': os.path.join(self.tmp.name, 'a.jpg'),
            'public_path': '/media/artist-images/1/a.jpg',
            'width': 100,
            'height': 100,
            'mime_type': 'image/jpeg',
            'file_size': 10,
        }

    def add_provider(self, name, candidates):
        provider = MagicMock()
        provider.name = name
        provider.get_artist_images.return_value = candidates
        self.fetcher.providers.append(provider)
        return provider


class ConstructionTest(unittest.TestCase):
    def test_without_a_connection_one_is_opened_through_the_shared_connector(self):
        with patch.object(fetcher_module, 'DatabaseConnector') as connector:
            instance = ArtistImageFetcher()
        connector.return_value.connect.assert_called_once()
        self.assertEqual(len(instance.providers), 3)
        self.assertEqual([p.name for p in instance.providers], ['spotify', 'soundcloud', 'lastfm'])

    def test_the_storage_location_falls_back_to_the_library_default(self):
        with patch.dict(os.environ, {}, clear=True):
            instance = ArtistImageFetcher(db_conn=MagicMock())
        self.assertEqual(instance.storage.storage_path, '/mnt/music/artists')
        self.assertEqual(instance.storage.public_base_url, '/media/artist-images')


class FetchForArtistTest(FetcherTestCase):
    def test_an_unknown_artist_id_is_reported_as_a_failure(self):
        self.cursor.fetchone.return_value = None
        self.assertFalse(self.fetcher.fetch_for_artist(1))

    def test_an_artist_that_already_has_an_image_is_skipped(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Angerfist', 'mbid': None, 'primary_image_id': 9}
        self.assertTrue(self.fetcher.fetch_for_artist(1))
        self.fetcher.mb_provider.get_artist_metadata.assert_not_called()

    def test_force_refresh_processes_an_artist_that_already_has_an_image(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Angerfist', 'mbid': None, 'primary_image_id': 9}
        self.cursor.fetchall.return_value = []
        self.assertFalse(self.fetcher.fetch_for_artist(1, force_refresh=True))
        self.fetcher.mb_provider.get_artist_metadata.assert_called_once()

    def test_a_supplied_name_skips_the_name_lookup_but_still_reads_the_mbid(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': 'mb1', 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.fetcher.fetch_for_artist(1, 'Angerfist')
        self.fetcher.mb_provider.get_artist_metadata.assert_called_once_with('Angerfist', 'mb1')

    def test_an_artist_row_that_is_gone_leaves_the_mbid_empty(self):
        self.cursor.fetchone.return_value = None
        self.cursor.fetchall.return_value = []
        self.fetcher.fetch_for_artist(1, 'Angerfist')
        self.fetcher.mb_provider.get_artist_metadata.assert_called_once_with('Angerfist', None)

    def test_musicbrainz_metadata_backfills_the_mbid_and_the_external_ids(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.fetcher.mb_provider.get_artist_metadata.return_value = {
            'mbid': 'mb-new',
            'name': 'Angerfist',
            'external_ids': {'spotify': 'sp1'},
        }
        provider = self.add_provider('spotify', [])
        self.fetcher.fetch_for_artist(1, 'Angerfist')
        self.assertEqual(provider.get_artist_images.call_args.args[1], 'mb-new')
        self.assertEqual(provider.get_artist_images.call_args.args[2], {'spotify': 'sp1'})
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertTrue(any('UPDATE library_artists SET mbid' in s for s in statements))
        self.assertTrue(any('INSERT INTO artist_external_ids' in s for s in statements))

    def test_an_external_id_that_is_already_stored_is_not_written_again(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': 'mb1', 'primary_image_id': None}
        self.cursor.fetchall.return_value = [{'source': 'spotify', 'external_id': 'sp-existing'}]
        self.fetcher.mb_provider.get_artist_metadata.return_value = {
            'mbid': 'mb1',
            'name': 'Angerfist',
            'external_ids': {'spotify': 'sp-other'},
        }
        self.add_provider('spotify', [])
        self.fetcher.fetch_for_artist(1, 'Angerfist')
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertFalse(any('INSERT INTO artist_external_ids' in s for s in statements))

    def test_a_provider_that_raises_does_not_stop_the_others(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        broken = self.add_provider('spotify', [])
        broken.get_artist_images.side_effect = RuntimeError('api down')
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))

    def test_without_a_confident_candidate_the_artist_is_marked_as_failed(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Someone Else', 'url': 'https://img.test/a.jpg'}]
        )
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertTrue(any('image_status = %s' in s for s in statements))

    def test_the_most_confident_candidate_wins(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm',
            [
                {'source': 'lastfm', 'source_id': 'weak', 'name': 'Angerfst', 'url': 'https://img.test/weak.jpg'},
                {'source': 'lastfm', 'source_id': 'strong', 'name': 'Angerfist', 'url': 'https://img.test/strong.jpg'},
            ],
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        self.fetcher.downloader.download.assert_called_once_with('https://img.test/strong.jpg')

    def test_a_candidate_that_already_carries_its_bytes_is_not_downloaded_again(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm',
            [
                {
                    'source': 'lastfm',
                    'source_id': 'l1',
                    'name': 'Angerfist',
                    'url': 'https://img.test/a.jpg',
                    'image_data': b'inline',
                }
            ],
        )
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        self.fetcher.downloader.download.assert_not_called()
        self.assertEqual(self.fetcher.storage.save_image.call_args.args[2], b'inline')

    def test_a_download_that_yields_nothing_marks_the_artist_as_failed(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = None
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Angerfist'))

    def test_a_storage_error_marks_the_artist_as_failed(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.fetcher.storage.save_image.side_effect = RuntimeError('disk full')
        self.assertFalse(self.fetcher.fetch_for_artist(1, 'Angerfist'))

    def test_a_successful_fetch_records_the_image_and_promotes_it_to_primary(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.cursor.lastrowid = 55
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        self.assertTrue(self.fetcher.fetch_for_artist(1, 'Angerfist'))
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertTrue(any('INSERT INTO library_artist_images' in s for s in statements))
        self.assertTrue(any('is_primary = 1' in s for s in statements))
        self.assertTrue(any("image_status = 'active'" in s for s in statements))


class ManifestTest(FetcherTestCase):
    def run_one_successful_fetch(self):
        self.cursor.fetchone.return_value = {'id': 1, 'mbid': None, 'primary_image_id': None}
        self.cursor.fetchall.return_value = []
        self.add_provider(
            'lastfm', [{'source': 'lastfm', 'source_id': 'l1', 'name': 'Angerfist', 'url': 'https://img.test/a.jpg'}]
        )
        self.fetcher.downloader.download.return_value = b'binary'
        return self.fetcher.fetch_for_artist(1, 'Angerfist')

    def manifest(self):
        with open(os.path.join(self.tmp.name, 'manifest.json')) as handle:
            return json.load(handle)

    def test_the_manifest_gets_an_entry_for_the_artist(self):
        self.assertTrue(self.run_one_successful_fetch())
        entries = self.manifest()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['artist_id'], 1)
        self.assertEqual(entries[0]['name'], 'Angerfist')
        self.assertEqual(entries[0]['thumb_160'], '/media/artist-images/1/thumb_160.jpg')

    def test_an_existing_entry_for_the_same_artist_is_replaced(self):
        with open(os.path.join(self.tmp.name, 'manifest.json'), 'w') as handle:
            json.dump([{'artist_id': 1, 'name': 'Old'}, {'artist_id': 2, 'name': 'Other'}], handle)
        self.assertTrue(self.run_one_successful_fetch())
        entries = self.manifest()
        self.assertEqual(sorted(e['artist_id'] for e in entries), [1, 2])
        self.assertEqual([e for e in entries if e['artist_id'] == 1][0]['name'], 'Angerfist')

    def test_a_corrupt_manifest_is_replaced_rather_than_crashing_the_run(self):
        with open(os.path.join(self.tmp.name, 'manifest.json'), 'w') as handle:
            handle.write('{not json')
        self.assertTrue(self.run_one_successful_fetch())
        self.assertEqual(len(self.manifest()), 1)

    def test_a_manifest_that_cannot_be_written_does_not_fail_the_fetch(self):
        self.fetcher.storage.storage_path = '/does/not/exist'
        self.assertTrue(self.run_one_successful_fetch())


if __name__ == '__main__':
    unittest.main()
