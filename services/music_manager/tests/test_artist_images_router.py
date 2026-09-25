"""Coverage for the /api/artists router: search, the image manager, and the fetch tasks."""

import base64
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers import artist_images as artist_images_router

API_KEY = resolve_system_api_key()
# Captured before any test patches it, for the tests that need its URL checks.
REAL_DOWNLOAD = artist_images_router.download_public_image


class ArtistImagesTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patcher = patch.object(artist_images_router, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        artist_images_router.fetch_progress.update(
            {'active': False, 'total': 0, 'current': 0, 'last_artist': None, 'status': 'idle', 'message': None}
        )

    def statements(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]


class AuthTest(unittest.TestCase):
    def test_a_request_without_a_key_is_unauthorized(self):
        self.assertEqual(TestClient(app).get('/api/artists/search').status_code, 401)

    def test_a_user_key_that_verifies_is_accepted(self):
        with (
            patch.object(users_router, 'verify_token', return_value={'status': 'ok', 'type': 'user'}),
            patch.object(artist_images_router, 'get_db_connection', return_value=None),
        ):
            response = TestClient(app).get('/api/artists/search', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 500)

    def test_a_key_that_does_not_verify_is_rejected(self):
        with patch.object(users_router, 'verify_token', side_effect=HTTPException(status_code=403)):
            response = TestClient(app).get('/api/artists/search', headers={'x-api-key': 'bad'})
        self.assertEqual(response.status_code, 403)


class SearchTest(ArtistImagesTestCase):
    def test_an_empty_search_lists_the_artists_that_have_an_image(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'Angerfist'}]
        response = self.client.get('/api/artists/search', headers=self.headers)
        self.assertEqual(response.json()[0]['name'], 'Angerfist')
        self.assertNotIn('LIKE', self.statements()[0])

    def test_a_search_term_narrows_the_result(self):
        self.cursor.fetchall.return_value = []
        self.client.get('/api/artists/search?q=anger', headers=self.headers)
        self.assertEqual(self.cursor.execute.call_args.args[1], ('%anger%',))

    def test_search_all_lists_every_artist(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'Angerfist'}]
        response = self.client.get('/api/artists/search-all', headers=self.headers)
        self.assertEqual(response.json()[0]['name'], 'Angerfist')
        self.assertNotIn('LIKE', self.statements()[0])

    def test_search_all_also_accepts_a_search_term(self):
        self.cursor.fetchall.return_value = []
        self.client.get('/api/artists/search-all?q=anger', headers=self.headers)
        self.assertEqual(self.cursor.execute.call_args.args[1], ('%anger%',))

    def test_the_image_stats_are_reported(self):
        self.cursor.fetchone.side_effect = [{'total': 10}, {'with_image': 4}]
        body = self.client.get('/api/artists/images/stats', headers=self.headers).json()
        self.assertEqual(body, {'total_artists': 10, 'artists_with_images': 4, 'artists_without_images': 6})

    def test_the_fetch_progress_is_reported(self):
        body = self.client.get('/api/artists/fetch-progress', headers=self.headers).json()
        self.assertEqual(body['status'], 'idle')


class ManageSearchTest(ArtistImagesTestCase):
    def search(self, query=''):
        self.cursor.fetchone.return_value = {'total': 1}
        self.cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Angerfist', 'primary_image_id': None, 'image_status': None, 'image_updated_at': None}
        ]
        return self.client.get(f'/api/artists/manage/search{query}', headers=self.headers)

    def test_every_artist_is_returned_with_its_image_metadata(self):
        body = self.search().json()
        self.assertEqual(body['total'], 1)
        self.assertFalse(body['items'][0]['has_image'])

    def test_an_invalid_only_filter_is_rejected(self):
        response = self.client.get('/api/artists/manage/search?only=maybe', headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_the_with_filter_narrows_to_artists_that_have_an_image(self):
        self.search('?only=with')
        self.assertIn('primary_image_id IS NOT NULL', self.statements()[0])

    def test_the_without_filter_narrows_to_artists_that_have_none(self):
        self.search('?only=without')
        self.assertIn('primary_image_id IS NULL', self.statements()[0])

    def test_a_search_term_is_combined_with_the_filter(self):
        self.search('?q=anger&only=with')
        self.assertIn('a.name LIKE %s', self.statements()[0])
        self.assertIn('AND', self.statements()[0])

    def test_the_limit_is_capped(self):
        self.search('?limit=9999')
        self.assertEqual(self.cursor.execute.call_args.args[1][-2], artist_images_router.MANAGE_SEARCH_MAX_LIMIT)

    def test_a_zero_limit_is_raised_to_one(self):
        self.search('?limit=0')
        self.assertEqual(self.cursor.execute.call_args.args[1][-2], 1)

    def test_a_negative_offset_becomes_zero(self):
        self.search('?offset=-5')
        self.assertEqual(self.cursor.execute.call_args.args[1][-1], 0)

    def test_a_missing_count_row_reports_zero(self):
        self.cursor.fetchone.return_value = None
        self.cursor.fetchall.return_value = []
        body = self.client.get('/api/artists/manage/search', headers=self.headers).json()
        self.assertEqual(body['total'], 0)

    def test_a_timestamp_is_serialized_as_an_iso_string(self):
        from datetime import datetime

        self.cursor.fetchone.return_value = {'total': 1}
        self.cursor.fetchall.return_value = [
            {
                'id': 1,
                'name': 'A',
                'primary_image_id': 2,
                'image_status': 'active',
                'image_updated_at': datetime(2026, 1, 2, 3, 4, 5),
            }
        ]
        body = self.client.get('/api/artists/manage/search', headers=self.headers).json()
        self.assertEqual(body['items'][0]['image_updated_at'], '2026-01-02T03:04:05')
        self.assertTrue(body['items'][0]['has_image'])


class ListArtistImagesTest(ArtistImagesTestCase):
    def test_all_stored_images_are_listed(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Angerfist', 'primary_image_id': 5}
        self.cursor.fetchall.return_value = [{'id': 5, 'cached_path': '/mnt/a.jpg'}]
        with patch.object(artist_images_router.os.path, 'exists', return_value=True):
            body = self.client.get('/api/artists/1/images', headers=self.headers).json()
        self.assertEqual(body['artist_name'], 'Angerfist')
        self.assertTrue(body['images'][0]['exists_on_disk'])

    def test_an_image_row_without_a_file_is_flagged(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Angerfist', 'primary_image_id': 5}
        self.cursor.fetchall.return_value = [{'id': 5, 'cached_path': None}]
        body = self.client.get('/api/artists/1/images', headers=self.headers).json()
        self.assertFalse(body['images'][0]['exists_on_disk'])

    def test_an_unknown_artist_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        self.assertEqual(self.client.get('/api/artists/1/images', headers=self.headers).status_code, 404)


class ManualImageTest(ArtistImagesTestCase):
    def setUp(self):
        super().setUp()
        self.storage_module = MagicMock()
        self.storage = self.storage_module.ImageStorage.return_value
        self.storage.save_image.return_value = {
            'cached_path': '/mnt/a.jpg',
            'public_path': '/media/a.jpg',
            'width': 100,
            'height': 100,
            'mime_type': 'image/jpeg',
            'file_size': 10,
        }
        patcher = patch.dict(sys.modules, {'services.music_manager.artist_image_fetcher.storage': self.storage_module})
        patcher.start()
        self.addCleanup(patcher.stop)
        download_patcher = patch.object(artist_images_router, 'download_public_image')
        self.download = download_patcher.start()
        self.addCleanup(download_patcher.stop)

    def test_an_image_url_is_downloaded_and_becomes_the_primary_image(self):
        self.download.return_value = b'binary'
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Angerfist'}
        self.cursor.lastrowid = 9
        body = self.client.post(
            '/api/artists/1/image/url', headers=self.headers, json={'url': 'https://img.test/a.jpg'}
        ).json()
        self.assertEqual(body['image_id'], 9)
        self.assertTrue(any('is_primary = 1' in s for s in self.statements()))

    def test_a_non_http_url_is_rejected(self):
        # The real download helper, not the setUp mock: the scheme check lives there.
        self.download.side_effect = REAL_DOWNLOAD
        response = self.client.post(
            '/api/artists/1/image/url', headers=self.headers, json={'url': 'ftp://img.test/a.jpg'}
        )
        self.assertEqual(response.status_code, 400)

    def test_a_download_that_fails_is_reported(self):
        self.download.side_effect = RuntimeError('404')
        response = self.client.post(
            '/api/artists/1/image/url', headers=self.headers, json={'url': 'https://img.test/a.jpg'}
        )
        self.assertEqual(response.status_code, 400)

    def test_a_download_that_yields_nothing_is_reported(self):
        self.download.return_value = None
        response = self.client.post(
            '/api/artists/1/image/url', headers=self.headers, json={'url': 'https://img.test/a.jpg'}
        )
        self.assertEqual(response.status_code, 400)

    def test_base64_image_bytes_can_be_uploaded(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Angerfist'}
        self.cursor.lastrowid = 9
        payload = base64.b64encode(b'binary').decode()
        body = self.client.post('/api/artists/1/image/upload', headers=self.headers, json={'data': payload}).json()
        self.assertEqual(body['image_id'], 9)

    def test_a_data_url_prefix_is_stripped(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Angerfist'}
        self.cursor.lastrowid = 9
        payload = 'data:image/png;base64,' + base64.b64encode(b'binary').decode()
        response = self.client.post('/api/artists/1/image/upload', headers=self.headers, json={'data': payload})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.storage.save_image.call_args.args[2], b'binary')

    def test_data_that_is_not_base64_is_rejected(self):
        response = self.client.post('/api/artists/1/image/upload', headers=self.headers, json={'data': 'not base64!!'})
        self.assertEqual(response.status_code, 400)

    def test_empty_data_is_rejected(self):
        response = self.client.post('/api/artists/1/image/upload', headers=self.headers, json={'data': ''})
        self.assertEqual(response.status_code, 400)

    def test_an_upload_for_an_unknown_artist_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        payload = base64.b64encode(b'binary').decode()
        response = self.client.post('/api/artists/1/image/upload', headers=self.headers, json={'data': payload})
        self.assertEqual(response.status_code, 404)

    def test_bytes_that_are_not_an_image_are_rejected(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Angerfist'}
        self.storage.save_image.side_effect = RuntimeError('cannot identify image file')
        payload = base64.b64encode(b'binary').decode()
        response = self.client.post('/api/artists/1/image/upload', headers=self.headers, json={'data': payload})
        self.assertEqual(response.status_code, 400)


class PrimaryImageTest(ArtistImagesTestCase):
    def test_an_existing_image_can_be_promoted_to_primary(self):
        self.cursor.fetchone.return_value = {'id': 5}
        body = self.client.post('/api/artists/1/image/select/5', headers=self.headers).json()
        self.assertEqual(body, {'status': 'ok', 'artist_id': 1, 'image_id': 5})

    def test_promoting_an_image_of_another_artist_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        response = self.client.post('/api/artists/1/image/select/5', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_the_primary_image_can_be_cleared_without_losing_the_files(self):
        self.cursor.fetchone.return_value = {'id': 1}
        body = self.client.post('/api/artists/1/image/clear', headers=self.headers).json()
        self.assertEqual(body, {'status': 'ok', 'artist_id': 1})
        # `cleared`, not `none`: the start-up bulk run skips it instead of undoing the clear.
        self.assertTrue(any("image_status = 'cleared'" in s for s in self.statements()))
        self.assertFalse(any('DELETE' in s for s in self.statements()))

    def test_clearing_for_an_unknown_artist_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        self.assertEqual(self.client.post('/api/artists/1/image/clear', headers=self.headers).status_code, 404)

    def test_clearing_also_removes_the_published_copies(self):
        """Bug 080: `primary.jpg` kept serving the portrait that had just been cleared."""
        self.cursor.fetchone.return_value = {'id': 1}
        with patch.object(artist_images_router, '_image_storage') as storage:
            self.client.post('/api/artists/1/image/clear', headers=self.headers)
        storage.return_value.unpublish_primary.assert_called_once_with(1)

    def test_a_file_system_failure_does_not_undo_a_committed_clear(self):
        self.cursor.fetchone.return_value = {'id': 1}
        with patch.object(artist_images_router, '_image_storage') as storage:
            storage.return_value.unpublish_primary.side_effect = PermissionError('read-only')
            response = self.client.post('/api/artists/1/image/clear', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.conn.commit.assert_called()

    def test_selecting_an_image_publishes_it(self):
        self.cursor.fetchone.return_value = {'id': 5, 'cached_path': '/mnt/artists/1/spotify-abc.jpg'}
        with patch.object(artist_images_router, '_image_storage') as storage:
            self.client.post('/api/artists/1/image/select/5', headers=self.headers)
        storage.return_value.publish_primary.assert_called_once_with(1, '/mnt/artists/1/spotify-abc.jpg')


class ServeArtistImageTest(ArtistImagesTestCase):
    def test_a_cached_image_is_served_from_disk(self):
        self.cursor.fetchone.return_value = {'cached_path': '/mnt/a.jpg'}
        with (
            patch.object(artist_images_router.os.path, 'exists', return_value=True),
            patch.object(artist_images_router, 'FileResponse', return_value={'served': True}) as file_response,
        ):
            self.client.get('/api/artists/Angerfist/image')
        file_response.assert_called_once_with('/mnt/a.jpg')

    # A miss is a 404 and nothing else: the fetch this endpoint used to schedule was
    # attached to an exception response, which Starlette never runs, and since !884
    # every uncovered track row asks here -- a lookup per miss would be a lookup storm.
    def test_a_missing_image_reports_not_found_without_starting_a_lookup(self):
        self.cursor.fetchone.return_value = None
        with patch.object(artist_images_router, 'trigger_fetch_by_id') as trigger:
            response = self.client.get('/api/artists/Angerfist/image')
        self.assertEqual(response.status_code, 404)
        trigger.assert_not_called()

    def test_a_row_whose_file_disappeared_also_reports_not_found(self):
        self.cursor.fetchone.return_value = {'cached_path': '/mnt/gone.jpg'}
        with (
            patch.object(artist_images_router.os.path, 'exists', return_value=False),
            patch.object(artist_images_router, 'trigger_fetch_by_id') as trigger,
        ):
            response = self.client.get('/api/artists/Angerfist/image')
        self.assertEqual(response.status_code, 404)
        trigger.assert_not_called()


class FetchEndpointTest(ArtistImagesTestCase):
    def test_a_global_fetch_is_started_in_the_background(self):
        with patch.object(artist_images_router, 'run_fetch_missing') as task:
            body = self.client.post('/api/artists/fetch-missing', headers=self.headers).json()
        self.assertEqual(body['status'], 'ok')
        task.assert_called_once()

    def test_a_second_global_fetch_is_refused_while_one_is_running(self):
        artist_images_router.fetch_progress['active'] = True
        with patch.object(artist_images_router, 'run_fetch_missing') as task:
            body = self.client.post('/api/artists/fetch-images', headers=self.headers).json()
        self.assertEqual(body['status'], 'error')
        task.assert_not_called()

    def test_a_single_artist_fetch_is_started_in_the_background(self):
        with patch.object(artist_images_router, 'trigger_fetch_by_id') as task:
            body = self.client.post('/api/artists/7/fetch-image', headers=self.headers).json()
        self.assertEqual(body['status'], 'ok')
        task.assert_called_once_with(7, False)

    def test_force_is_passed_on_so_a_cleared_portrait_can_be_fetched_again(self):
        with patch.object(artist_images_router, 'trigger_fetch_by_id') as task:
            self.client.post('/api/artists/7/fetch-image?force=true', headers=self.headers)
        task.assert_called_once_with(7, True)


class BackgroundFetchTest(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        self.fetcher_module = MagicMock()
        self.fetcher = self.fetcher_module.ArtistImageFetcher.return_value
        # A MagicMock attribute is truthy, and a blind fetcher stops the run before it asks.
        self.fetcher.blind = False
        self.fetcher.log_run_summary.return_value = {
            'deferred': 0,
            'rate_limit_pauses': 0,
            'pause_seconds': 0.0,
            'provider_failures': {},
            'download_failures': 0,
        }
        patches = [
            patch.object(artist_images_router, 'get_db_connection', return_value=self.conn),
            patch.dict(sys.modules, {'services.music_manager.artist_image_fetcher.fetcher': self.fetcher_module}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        artist_images_router.fetch_progress.update({'active': False, 'status': 'idle'})

    def test_every_artist_without_an_image_is_fetched_and_the_result_reported(self):
        self.cursor.fetchone.return_value = {'count': 2}
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'One'}, {'id': 2, 'name': 'Two'}]
        self.fetcher.fetch_for_artist.side_effect = [True, False]
        artist_images_router.run_fetch_missing()
        self.assertEqual(artist_images_router.fetch_progress['status'], 'completed')
        self.assertIn('1 succeeded, 1 failed', artist_images_router.fetch_progress['message'])
        self.assertFalse(artist_images_router.fetch_progress['active'])

    def test_the_run_is_bracketed_by_a_start_and_one_summary(self):
        self.cursor.fetchone.return_value = {'count': 2}
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'One'}, {'id': 2, 'name': 'Two'}]
        self.fetcher.fetch_for_artist.return_value = False
        artist_images_router.run_fetch_missing()
        self.fetcher.start_run.assert_called_once_with()
        self.fetcher.log_run_summary.assert_called_once_with()

    def test_a_fetcher_that_raises_counts_as_a_failure(self):
        self.cursor.fetchone.return_value = {'count': 1}
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'One'}]
        self.fetcher.fetch_for_artist.side_effect = RuntimeError('api down')
        artist_images_router.run_fetch_missing()
        self.assertIn('0 succeeded, 1 failed', artist_images_router.fetch_progress['message'])

    def test_the_completion_message_carries_the_run_counters(self):
        self.cursor.fetchone.return_value = {'count': 2}
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'One'}, {'id': 2, 'name': 'Two'}]
        self.fetcher.fetch_for_artist.return_value = False
        self.fetcher.log_run_summary.return_value.update(
            {'deferred': 1, 'download_failures': 1, 'provider_failures': {'musicbrainz': 2}}
        )
        artist_images_router.run_fetch_missing()
        self.assertIn('1 deferred, 1 downloads failed, 0 errors', artist_images_router.fetch_progress['message'])

    # Whatever breaks one artist here breaks the next as well; one push is enough.
    def test_only_the_first_artist_that_raises_is_an_error(self):
        self.cursor.fetchone.return_value = {'count': 3}
        self.cursor.fetchall.return_value = [{'id': i, 'name': f'A{i}'} for i in range(3)]
        self.fetcher.fetch_for_artist.side_effect = RuntimeError('database gone')
        with self.assertLogs(artist_images_router.logger.name, level='INFO') as logs:
            artist_images_router.run_fetch_missing()
        failures = [r for r in logs.records if 'Failed to fetch for' in r.getMessage()]
        self.assertEqual([r.levelname for r in failures], ['ERROR', 'INFO', 'INFO'])
        self.assertIn('3 errors', artist_images_router.fetch_progress['message'])

    def test_a_library_where_nothing_is_missing_finishes_immediately(self):
        self.cursor.fetchone.return_value = {'count': 5}
        self.cursor.fetchall.return_value = []
        artist_images_router.run_fetch_missing()
        self.assertEqual(artist_images_router.fetch_progress['status'], 'completed')
        self.fetcher.fetch_for_artist.assert_not_called()

    def test_a_fetcher_without_a_provider_stops_before_asking_anyone(self):
        """A run with no configured provider learns nothing about anybody, so it must not
        walk the list -- that walk is how 45.000 artists became `failed` in August 2026."""
        self.fetcher.blind = True
        self.cursor.fetchone.return_value = {'count': 2}
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'One'}]
        artist_images_router.run_fetch_missing()
        self.assertEqual(artist_images_router.fetch_progress['status'], 'failed')
        self.assertIn('Spotify client id', artist_images_router.fetch_progress['message'])
        self.assertFalse(artist_images_router.fetch_progress['active'])
        self.fetcher.fetch_for_artist.assert_not_called()
        self.cursor.execute.assert_not_called()

    def test_a_database_outage_marks_the_fetch_as_failed(self):
        with patch.object(artist_images_router, 'get_db_connection', return_value=None):
            artist_images_router.run_fetch_missing()
        self.assertEqual(artist_images_router.fetch_progress['status'], 'failed')

    def test_an_unexpected_failure_marks_the_fetch_as_failed(self):
        self.fetcher_module.ArtistImageFetcher.side_effect = RuntimeError('no credentials')
        artist_images_router.run_fetch_missing()
        self.assertEqual(artist_images_router.fetch_progress['status'], 'failed')

    def test_a_recent_failure_is_left_alone_until_the_cooldown_passes(self):
        """The startup crawl must not re-ask a third party for every hopeless name on
        every boot, so the query excludes artists whose last attempt failed recently."""
        self.cursor.fetchone.return_value = {'count': 1}
        self.cursor.fetchall.return_value = []
        with patch.dict(os.environ, {'ARTIST_IMAGE_RETRY_AFTER_DAYS': '14'}):
            artist_images_router.run_fetch_missing()
        sql, params = self.cursor.execute.call_args_list[-1][0]
        self.assertIn('image_status', sql)
        self.assertIn("<> 'failed'", sql)
        self.assertIn('INTERVAL %s DAY', sql)
        self.assertEqual(params, (14,))

    def test_an_artist_whose_portrait_was_cleared_is_not_fetched_again(self):
        """Clearing set `none`, which this query picked up on the next boot."""
        self.cursor.fetchone.return_value = {'count': 1}
        self.cursor.fetchall.return_value = []
        artist_images_router.run_fetch_missing()
        sql = self.cursor.execute.call_args_list[-1][0][0]
        self.assertIn("image_status <> 'cleared'", sql)

    def test_the_cooldown_defaults_to_thirty_days(self):
        self.cursor.fetchone.return_value = {'count': 1}
        self.cursor.fetchall.return_value = []
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('ARTIST_IMAGE_RETRY_AFTER_DAYS', None)
            artist_images_router.run_fetch_missing()
        self.assertEqual(self.cursor.execute.call_args_list[-1][0][1], (30,))

    def test_a_single_artist_fetch_by_id_forces_a_refresh(self):
        self.cursor.fetchone.return_value = {'name': 'Angerfist'}
        artist_images_router.trigger_fetch_by_id(7)
        self.fetcher.fetch_for_artist.assert_called_once_with(
            7, 'Angerfist', force_refresh=True, override_cleared=False
        )

    def test_a_forced_single_artist_fetch_overrides_a_cleared_portrait(self):
        self.cursor.fetchone.return_value = {'name': 'Angerfist'}
        artist_images_router.trigger_fetch_by_id(7, force=True)
        self.fetcher.fetch_for_artist.assert_called_once_with(7, 'Angerfist', force_refresh=True, override_cleared=True)

    def test_an_unknown_artist_id_fetches_nothing(self):
        self.cursor.fetchone.return_value = None
        artist_images_router.trigger_fetch_by_id(7)
        self.fetcher.fetch_for_artist.assert_not_called()

    def test_a_fetch_by_id_without_a_database_does_nothing(self):
        with patch.object(artist_images_router, 'get_db_connection', return_value=None):
            artist_images_router.trigger_fetch_by_id(7)
        self.fetcher.fetch_for_artist.assert_not_called()

    def test_a_failing_fetch_by_id_is_swallowed(self):
        self.fetcher_module.ArtistImageFetcher.side_effect = RuntimeError('boom')
        with patch('builtins.print'):
            artist_images_router.trigger_fetch_by_id(7)  # must not raise


class SyncImagesToServerTest(unittest.TestCase):
    def setUp(self):
        self.muma_conn = MagicMock()
        self.muma_cursor = MagicMock()
        self.muma_conn.cursor.return_value.__enter__.return_value = self.muma_cursor
        self.muma_conn.cursor.return_value.__exit__.return_value = False
        self.server_conn = MagicMock()
        self.server_cursor = self.server_conn.cursor.return_value

    def sync(self):
        with patch('builtins.print'):
            artist_images_router.sync_artist_images_to_server(self.muma_conn, self.server_conn)

    def image_row(self):
        return {
            'artist_name': 'Angerfist',
            'cached_path': '/mnt/a.jpg',
            'width': 1,
            'height': 1,
            'mime_type': 'image/jpeg',
            'file_size': 10,
        }

    def test_a_new_image_and_artwork_row_are_created_and_linked(self):
        self.muma_cursor.fetchall.return_value = [self.image_row()]
        self.server_cursor.fetchone.side_effect = [(3, None), None, None]
        self.server_cursor.lastrowid = 11
        self.sync()
        statements = [call.args[0] for call in self.server_cursor.execute.call_args_list]
        self.assertTrue(any('INSERT INTO image' in s for s in statements))
        self.assertTrue(any('INSERT INTO artwork' in s for s in statements))
        self.assertTrue(any('UPDATE artist SET preferred_artwork_id' in s for s in statements))

    def test_an_image_the_server_already_knows_is_reused(self):
        self.muma_cursor.fetchall.return_value = [self.image_row()]
        self.server_cursor.fetchone.side_effect = [(3, None), (11,), (12,)]
        self.sync()
        statements = [call.args[0] for call in self.server_cursor.execute.call_args_list]
        self.assertFalse(any('INSERT INTO image' in s for s in statements))
        self.assertFalse(any('INSERT INTO artwork' in s for s in statements))
        self.assertTrue(any('UPDATE artist' in s for s in statements))

    def test_an_artist_already_pointing_at_the_artwork_is_not_written(self):
        # After the first pass this is every artist. Writing them anyway held the server's
        # write lock for thirty seconds an hour, and the player aborts a rating after one.
        self.muma_cursor.fetchall.return_value = [self.image_row()]
        self.server_cursor.fetchone.side_effect = [(3, 12), (11,), (12,)]
        self.sync()
        statements = [call.args[0] for call in self.server_cursor.execute.call_args_list]
        self.assertFalse(any(s.lstrip().startswith(('UPDATE', 'INSERT')) for s in statements))

    def test_an_artist_the_server_does_not_know_is_skipped(self):
        self.muma_cursor.fetchall.return_value = [self.image_row()]
        self.server_cursor.fetchone.return_value = None
        self.sync()
        statements = [call.args[0] for call in self.server_cursor.execute.call_args_list]
        self.assertFalse(any('UPDATE artist' in s for s in statements))

    def test_a_failing_sync_is_swallowed(self):
        self.muma_conn.cursor.side_effect = RuntimeError('database gone')
        self.sync()  # must not raise


class UnsetClearedArtworkTest(unittest.TestCase):
    """Bug 080: a cleared portrait stayed the server's artist artwork, so the player kept it."""

    def setUp(self):
        import sqlite3

        self.server_conn = sqlite3.connect(':memory:')
        self.server_conn.executescript(
            """
            CREATE TABLE image (id INTEGER PRIMARY KEY, absolute_file_path TEXT);
            CREATE TABLE artwork (id INTEGER PRIMARY KEY, image_id INTEGER);
            CREATE TABLE artist (id INTEGER PRIMARY KEY, name TEXT, preferred_artwork_id INTEGER);
            INSERT INTO image VALUES (1, '/mnt/artists/9/spotify-abc.jpg'), (2, '/music/Angerfist/artist.jpg');
            INSERT INTO artwork VALUES (10, 1), (20, 2);
            INSERT INTO artist VALUES (100, 'Angerfist', 10), (200, 'Miss K8', 20);
            """
        )
        self.addCleanup(self.server_conn.close)
        self.muma_conn = MagicMock()
        self.muma_cursor = MagicMock()
        self.muma_conn.cursor.return_value.__enter__.return_value = self.muma_cursor
        self.muma_conn.cursor.return_value.__exit__.return_value = False

    def artwork_of(self, artist_id):
        return self.server_conn.execute(
            'SELECT preferred_artwork_id FROM artist WHERE id = ?', (artist_id,)
        ).fetchone()[0]

    def unset(self):
        with patch('builtins.print'):
            return artist_images_router._unset_cleared_artwork_on_server(self.muma_conn, self.server_conn)

    def test_artwork_this_sync_gave_the_server_is_taken_back(self):
        self.muma_cursor.fetchall.return_value = [
            {'artist_name': 'Angerfist', 'cached_path': '/mnt/artists/9/spotify-abc.jpg'}
        ]
        self.assertEqual(self.unset(), 1)
        self.assertIsNone(self.artwork_of(100))
        self.assertEqual(self.artwork_of(200), 20)
        sql = self.muma_cursor.execute.call_args.args[0]
        self.assertIn("image_status = 'cleared'", sql)

    def test_artwork_the_server_found_itself_is_left_alone(self):
        self.muma_cursor.fetchall.return_value = [{'artist_name': 'Miss K8', 'cached_path': '/mnt/artists/3/x.jpg'}]
        self.assertEqual(self.unset(), 0)
        self.assertEqual(self.artwork_of(200), 20)

    def test_nothing_cleared_means_nothing_written(self):
        self.muma_cursor.fetchall.return_value = []
        self.assertEqual(self.unset(), 0)
        self.assertEqual(self.artwork_of(100), 10)

    def test_the_full_sync_ends_with_this_pass(self):
        with patch.object(artist_images_router, '_unset_cleared_artwork_on_server') as unset:
            self.muma_cursor.fetchall.return_value = []
            with patch('builtins.print'):
                artist_images_router.sync_artist_images_to_server(self.muma_conn, self.server_conn)
        unset.assert_called_once_with(self.muma_conn, self.server_conn)


if __name__ == '__main__':
    unittest.main()
