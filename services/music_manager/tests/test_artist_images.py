import base64
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())


import services.music_manager.routers.users

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from fastapi.testclient import TestClient

from services.music_manager.main import app

ROUTER = 'services.music_manager.routers.artist_images'


def make_conn(cursor):
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


class ArtistImagesManagerTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'
        self.headers = {'X-API-Key': self.api_key}

    @patch(f'{ROUTER}.get_db_connection')
    def test_manage_search_returns_artists_with_and_without_images(self, mock_get_db):
        cursor = MagicMock()
        cursor.fetchone.return_value = {'total': 2}
        cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Daft Punk', 'primary_image_id': 11, 'image_status': 'active', 'image_updated_at': None,
             'width': 640, 'height': 640, 'mime_type': 'image/jpeg', 'file_size': 1234, 'source': 'spotify', 'original_url': 'http://x/y.jpg'},
            {'id': 2, 'name': 'Daft Monk', 'primary_image_id': None, 'image_status': 'failed', 'image_updated_at': None,
             'width': None, 'height': None, 'mime_type': None, 'file_size': None, 'source': None, 'original_url': None},
        ]
        mock_get_db.return_value = make_conn(cursor)

        res = self.client.get('/api/artists/manage/search?q=daft', headers=self.headers)

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['total'], 2)
        self.assertEqual([i['name'] for i in body['items']], ['Daft Punk', 'Daft Monk'])
        self.assertEqual([i['has_image'] for i in body['items']], [True, False])
        # The artist without an image must still be returned -- that is the whole
        # point of this endpoint versus /search.
        self.assertIsNone(body['items'][1]['primary_image_id'])

    @patch(f'{ROUTER}.get_db_connection')
    def test_manage_search_only_filter_is_applied_in_sql(self, mock_get_db):
        cursor = MagicMock()
        cursor.fetchone.return_value = {'total': 0}
        cursor.fetchall.return_value = []
        mock_get_db.return_value = make_conn(cursor)

        res = self.client.get('/api/artists/manage/search?only=without', headers=self.headers)

        self.assertEqual(res.status_code, 200)
        executed = ' '.join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn('a.primary_image_id IS NULL', executed)

    @patch(f'{ROUTER}.get_db_connection')
    def test_manage_search_rejects_unknown_only_value(self, mock_get_db):
        mock_get_db.return_value = make_conn(MagicMock())
        res = self.client.get('/api/artists/manage/search?only=bogus', headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_manage_search_requires_api_key(self):
        res = self.client.get('/api/artists/manage/search?q=daft')
        self.assertEqual(res.status_code, 401)

    @patch(f'{ROUTER}.get_db_connection')
    def test_list_artist_images(self, mock_get_db):
        cursor = MagicMock()
        cursor.fetchone.return_value = {'id': 1, 'name': 'Daft Punk', 'primary_image_id': 11}
        cursor.fetchall.return_value = [
            {'id': 11, 'source': 'spotify', 'source_id': 'sp1', 'original_url': None, 'cached_path': '/nope/a.jpg',
             'public_path': '/media/artist-images/1/a.jpg', 'width': 640, 'height': 640, 'mime_type': 'image/jpeg',
             'file_size': 10, 'confidence': 90, 'is_primary': 1},
        ]
        mock_get_db.return_value = make_conn(cursor)

        res = self.client.get('/api/artists/1/images', headers=self.headers)

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['primary_image_id'], 11)
        self.assertEqual(body['images'][0]['exists_on_disk'], False)

    @patch(f'{ROUTER}.get_db_connection')
    def test_select_primary_image(self, mock_get_db):
        cursor = MagicMock()
        cursor.fetchone.return_value = {'id': 12}
        conn = make_conn(cursor)
        mock_get_db.return_value = conn

        res = self.client.post('/api/artists/1/image/select/12', headers=self.headers)

        self.assertEqual(res.status_code, 200)
        executed = ' '.join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn('SET primary_image_id = %s', executed)
        conn.commit.assert_called_once()

    @patch(f'{ROUTER}.get_db_connection')
    def test_select_primary_image_rejects_foreign_image(self, mock_get_db):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        mock_get_db.return_value = make_conn(cursor)

        res = self.client.post('/api/artists/1/image/select/999', headers=self.headers)

        self.assertEqual(res.status_code, 404)

    @patch(f'{ROUTER}.get_db_connection')
    def test_clear_primary_image(self, mock_get_db):
        cursor = MagicMock()
        cursor.fetchone.return_value = {'id': 1}
        conn = make_conn(cursor)
        mock_get_db.return_value = conn

        res = self.client.post('/api/artists/1/image/clear', headers=self.headers)

        self.assertEqual(res.status_code, 200)
        executed = ' '.join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn('SET primary_image_id = NULL', executed)
        conn.commit.assert_called_once()

    @patch(f'{ROUTER}._store_manual_image')
    def test_upload_accepts_base64_data_url(self, mock_store):
        mock_store.return_value = {'status': 'ok', 'artist_id': 1, 'image_id': 42}
        payload = 'data:image/png;base64,' + base64.b64encode(b'fake-png-bytes').decode()

        res = self.client.post('/api/artists/1/image/upload', json={'data': payload}, headers=self.headers)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_store.call_args.args[1], b'fake-png-bytes')

    def test_upload_rejects_invalid_base64(self):
        res = self.client.post('/api/artists/1/image/upload', json={'data': 'not base64!!'}, headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_set_image_from_url_rejects_non_http_url(self):
        res = self.client.post('/api/artists/1/image/url', json={'url': 'file:///etc/passwd'}, headers=self.headers)
        self.assertEqual(res.status_code, 400)

    @patch(f'{ROUTER}._store_manual_image')
    @patch('services.music_manager.artist_image_fetcher.storage.ImageDownloader')
    def test_set_image_from_url_downloads_and_stores(self, mock_downloader, mock_store):
        mock_downloader.return_value.download.return_value = b'jpeg-bytes'
        mock_store.return_value = {'status': 'ok', 'artist_id': 1, 'image_id': 43}

        res = self.client.post('/api/artists/1/image/url', json={'url': 'https://example.com/a.jpg'}, headers=self.headers)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_store.call_args.args[1], b'jpeg-bytes')
        self.assertEqual(mock_store.call_args.kwargs['original_url'], 'https://example.com/a.jpg')


if __name__ == '__main__':
    unittest.main()
