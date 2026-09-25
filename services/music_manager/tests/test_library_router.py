"""Coverage for the /api/library and /api/scrobble routers."""

import hashlib
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils', 'DatabaseConnector')


import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers import library as library_router
from services.music_manager.routers import scrobbler as scrobbler_router

API_KEY = resolve_system_api_key()


class RouterTestCase(unittest.TestCase):
    module = None

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patcher = patch.object(self.module, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def statements(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]


class LibraryAuthTest(unittest.TestCase):
    def test_a_request_without_a_key_is_unauthorized(self):
        self.assertEqual(TestClient(app).get('/api/library/genres').status_code, 401)

    def test_a_user_key_that_verifies_is_accepted(self):
        with (
            patch.object(users_router, 'verify_token', return_value={'status': 'ok', 'type': 'user'}),
            patch.object(library_router, 'get_db_connection', return_value=None),
        ):
            response = TestClient(app).get('/api/library/genres', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 500)

    def test_a_key_no_account_holds_is_unauthenticated(self):
        refused = HTTPException(status_code=403, detail='Invalid API Key')
        with patch.object(users_router, 'verify_token', side_effect=refused):
            response = TestClient(app).get('/api/library/genres', headers={'x-api-key': 'bad'})
        self.assertEqual(response.status_code, 401)

    def test_a_disabled_account_is_forbidden_not_unauthenticated(self):
        # This router's own copy used to turn every verify_token exception into a 401.
        refused = HTTPException(status_code=403, detail='Account disabled')
        with patch.object(users_router, 'verify_token', side_effect=refused):
            response = TestClient(app).get('/api/library/genres', headers={'x-api-key': 'disabled'})
        self.assertEqual(response.status_code, 403)

    def test_a_key_that_verifies_without_an_ok_status_is_rejected(self):
        with patch.object(users_router, 'verify_token', return_value={'status': 'nope'}):
            response = TestClient(app).get('/api/library/genres', headers={'x-api-key': 'bad'})
        self.assertEqual(response.status_code, 401)


class LibraryTracksTest(RouterTestCase):
    module = library_router

    def test_tracks_are_returned_with_their_total(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'title': 'Track'}]
        self.cursor.fetchone.return_value = {'total': 1}
        response = self.client.get('/api/library/tracks', headers=self.headers)
        body = response.json()
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['page'], 1)

    def test_the_search_term_is_applied_to_title_artist_and_label(self):
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = {'total': 0}
        self.client.get('/api/library/tracks?q=anger', headers=self.headers)
        params = self.cursor.execute.call_args_list[0].args[1]
        self.assertEqual(params[:3], ('%anger%', '%anger%', '%anger%'))

    def test_paging_translates_into_an_offset(self):
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = {'total': 0}
        self.client.get('/api/library/tracks?page=3&limit=10', headers=self.headers)
        params = self.cursor.execute.call_args_list[0].args[1]
        self.assertEqual(params[-2:], (10, 20))

    def test_a_database_outage_is_reported_as_a_server_error(self):
        with patch.object(library_router, 'get_db_connection', return_value=None):
            response = self.client.get('/api/library/tracks', headers=self.headers)
        self.assertEqual(response.status_code, 500)

    def test_page_zero_is_refused_rather_than_a_negative_offset(self):
        # page=0 produced OFFSET -50, which MariaDB rejects: a 500 from a bad request.
        response = self.client.get('/api/library/tracks?page=0', headers=self.headers)
        self.assertEqual(response.status_code, 422)
        self.cursor.execute.assert_not_called()

    def test_the_page_size_is_capped(self):
        response = self.client.get(
            f'/api/library/tracks?limit={library_router.MAX_PAGE_SIZE + 1}', headers=self.headers
        )
        self.assertEqual(response.status_code, 422)
        self.cursor.execute.assert_not_called()

    def test_the_largest_page_is_still_served(self):
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = {'total': 0}
        response = self.client.get(f'/api/library/tracks?limit={library_router.MAX_PAGE_SIZE}', headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_rows_no_longer_scan_the_download_archives(self):
        # Two correlated LIKE '%basename%' scans per row over TEXT columns, read by nobody.
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = {'total': 0}
        self.client.get('/api/library/tracks', headers=self.headers)
        query = self.cursor.execute.call_args_list[0].args[0]
        self.assertNotIn('_archive', query)
        self.assertNotIn('sc_url', query)


class LibraryAdvancedTest(RouterTestCase):
    module = library_router

    def test_the_concatenated_genres_are_split_into_a_list(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'genres': 'Hardcore,Uptempo'}]
        self.cursor.fetchone.return_value = {'total': 1}
        response = self.client.get('/api/library/advanced', headers=self.headers)
        self.assertEqual(response.json()['tracks'][0]['genres'], ['Hardcore', 'Uptempo'])

    def test_a_track_without_genres_gets_an_empty_list(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'genres': None}]
        self.cursor.fetchone.return_value = {'total': 1}
        response = self.client.get('/api/library/advanced', headers=self.headers)
        self.assertEqual(response.json()['tracks'][0]['genres'], [])

    def test_page_zero_is_refused(self):
        response = self.client.get('/api/library/advanced?page=0&limit=10', headers=self.headers)
        self.assertEqual(response.status_code, 422)
        self.cursor.execute.assert_not_called()

    def test_the_first_page_starts_at_offset_zero(self):
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = {'total': 0}
        self.client.get('/api/library/advanced?page=1&limit=10', headers=self.headers)
        self.assertEqual(self.cursor.execute.call_args_list[0].args[1][-1], 0)

    def test_the_page_size_is_capped(self):
        response = self.client.get(
            f'/api/library/advanced?limit={library_router.MAX_PAGE_SIZE + 1}', headers=self.headers
        )
        self.assertEqual(response.status_code, 422)

    def test_a_database_outage_is_reported_as_a_server_error(self):
        with patch.object(library_router, 'get_db_connection', return_value=None):
            response = self.client.get('/api/library/advanced', headers=self.headers)
        self.assertEqual(response.status_code, 500)


class LibraryGenresTest(RouterTestCase):
    module = library_router

    def test_blacklisted_genres_are_left_out(self):
        self.cursor.fetchall.return_value = [{'genre': 'Hardcore', 'state': 'white', 'count': 3}]
        response = self.client.get('/api/library/genres', headers=self.headers)
        self.assertEqual(response.json()[0]['genre'], 'Hardcore')
        self.assertIn("state <> 'black'", self.statements()[0])

    def test_every_genre_carries_the_colour_its_tile_is_drawn_in(self):
        # The web UI and the app both draw a genre as a coloured tile. The colour comes from here
        # so neither of them owns a table that can drift away from the other.
        self.cursor.fetchall.return_value = [{'genre': 'Hardstyle', 'state': 'white', 'count': 3}]
        response = self.client.get('/api/library/genres', headers=self.headers)
        self.assertEqual(response.json()[0]['tint'], '#ff4d00')

    def test_a_genre_row_without_a_name_still_gets_a_colour(self):
        self.cursor.fetchall.return_value = [{'genre': None, 'state': 'white', 'count': 1}]
        response = self.client.get('/api/library/genres', headers=self.headers)
        self.assertRegex(response.json()[0]['tint'], r'^#[0-9a-f]{6}$')


class TrackByPathTest(RouterTestCase):
    """`GET /api/library/tracks/by-path`: what the player's details sheet asks MuMa for."""

    module = library_router

    MEDIA = {
        'file_path': '/mnt/music/Soundcloud/Complex/x.mp3',
        'file_path_hash': 'h',
        'track_id': 7,
        'track_uid': 'uid-7',
        'created_at': '2026-09-02 10:00:00',
    }

    def answer(self, *rows):
        """fetchone answers in query order; fetchall answers the channel query."""
        self.cursor.fetchone.side_effect = list(rows)

    def test_every_spelling_of_the_path_is_hashed_and_tried(self):
        self.answer(None)
        self.client.get('/api/library/tracks/by-path?path=Soundcloud/Complex/x.mp3', headers=self.headers)
        sql = self.statements()[0]
        params = self.cursor.execute.call_args_list[0].args[1]
        self.assertIn('file_path_hash IN', sql)
        self.assertIn(hashlib.sha256(b'/mnt/music/Soundcloud/Complex/x.mp3').hexdigest(), params)
        self.assertIn(hashlib.sha256(b'/music/Soundcloud/Complex/x.mp3').hexdigest(), params)
        self.assertIn(hashlib.sha256(b'Soundcloud/Complex/x.mp3').hexdigest(), params)

    def test_a_file_muma_never_scanned_is_a_not_found(self):
        self.answer(None)
        response = self.client.get('/api/library/tracks/by-path?path=nope.mp3', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_channels_tags_bpm_and_source_url_are_assembled(self):
        self.cursor.fetchall.return_value = [
            {'platform': 'soundcloud', 'name': 'Complex', 'label': None, 'artist': 'Complex'}
        ]
        self.answer(
            self.MEDIA,
            {'bpm': 103.0},
            {'ml_genre': 'hardstyle'},
            {
                'source': 'LABEL',
                'tags_json': '{"catalognumber": ["Q404PRO"], "publisher": ["QDance"]}',
                'recorded_at': '2026-09-10 08:00:00',
            },
            {'url': 'https://soundcloud.com/complex/x'},
        )
        response = self.client.get('/api/library/tracks/by-path?path=Soundcloud/Complex/x.mp3', headers=self.headers)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            body['channels'], [{'platform': 'soundcloud', 'name': 'Complex', 'label': None, 'artist': 'Complex'}]
        )
        self.assertEqual(body['tags'], {'catalognumber': ['Q404PRO'], 'publisher': ['QDance']})
        self.assertEqual(body['bpm'], 103.0)
        self.assertEqual(body['ml_genre'], 'hardstyle')
        self.assertEqual(body['source'], 'LABEL')
        self.assertEqual(body['source_url'], 'https://soundcloud.com/complex/x')
        self.assertEqual(body['source_platform'], 'soundcloud')
        self.assertEqual(body['added_at'], '2026-09-02 10:00:00')

    def test_the_archive_is_matched_on_the_whole_filename(self):
        self.cursor.fetchall.return_value = []
        self.answer(self.MEDIA, None, None, None, None, {'url': 'https://youtu.be/abc'})
        response = self.client.get('/api/library/tracks/by-path?path=Soundcloud/Complex/x.mp3', headers=self.headers)
        body = response.json()
        self.assertEqual(body['source_platform'], 'youtube')
        archive_statements = [s for s in self.statements() if 'archive' in s]
        self.assertEqual(len(archive_statements), 2)
        for statement in archive_statements:
            self.assertIn('filename IN', statement)
            self.assertNotIn('LIKE', statement)

    def test_an_unreadable_tags_json_yields_no_tags_rather_than_an_error(self):
        self.cursor.fetchall.return_value = []
        self.answer(
            self.MEDIA, None, None, {'source': 'YOUTUBE', 'tags_json': '{not json', 'recorded_at': None}, None, None
        )
        response = self.client.get('/api/library/tracks/by-path?path=x.mp3', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['tags'], {})
        self.assertEqual(response.json()['source'], 'YOUTUBE')

    def test_a_media_file_without_a_track_skips_the_track_joins(self):
        media = {**self.MEDIA, 'track_id': None, 'track_uid': None}
        self.answer(media, None, None, None)
        response = self.client.get('/api/library/tracks/by-path?path=x.mp3', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['channels'], [])
        self.assertIsNone(response.json()['bpm'])
        self.assertFalse(any('library_track_channels' in s for s in self.statements()))

    def test_a_database_outage_is_reported_as_a_server_error(self):
        with patch.object(library_router, 'get_db_connection', return_value=None):
            response = self.client.get('/api/library/tracks/by-path?path=x.mp3', headers=self.headers)
        self.assertEqual(response.status_code, 500)


class RerunParseTest(RouterTestCase):
    module = library_router

    def test_a_track_is_flagged_and_immediately_retagged(self):
        self.cursor.fetchone.return_value = {'file_path': '/music/a.mp3'}
        with (
            patch.object(library_router, 'ProcessedFilesHelper') as helper,
            patch('services.music_manager.routers.tagger.tagger_manager') as tagger,
            patch('services.music_manager.routers.scanner.scanner_manager') as scanner,
        ):
            response = self.client.post('/api/library/tracks/1/rerun-parse', headers=self.headers)
        self.assertEqual(response.json()['status'], 'ok')
        helper.return_value.mark_for_rescan.assert_called_once_with('/music/a.mp3', reason='rerun_parse')
        tagger.tag_single.assert_called_once_with('/music/a.mp3')
        scanner.scan_single.assert_called_once_with('/music/a.mp3')

    def test_a_track_without_a_file_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        with patch.object(library_router, 'ProcessedFilesHelper'):
            response = self.client.post('/api/library/tracks/1/rerun-parse', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_a_failing_immediate_retag_still_leaves_the_track_flagged(self):
        self.cursor.fetchone.return_value = {'file_path': '/music/a.mp3'}
        with (
            patch.object(library_router, 'ProcessedFilesHelper') as helper,
            patch('services.music_manager.routers.tagger.tagger_manager') as tagger,
        ):
            tagger.tag_single.side_effect = RuntimeError('tagger busy')
            response = self.client.post('/api/library/tracks/1/rerun-parse', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        helper.return_value.mark_for_rescan.assert_called_once()

    def test_a_file_can_also_be_flagged_by_path(self):
        with (
            patch.object(library_router, 'ProcessedFilesHelper') as helper,
            patch('services.music_manager.routers.tagger.tagger_manager') as tagger,
            patch('services.music_manager.routers.scanner.scanner_manager') as scanner,
        ):
            response = self.client.post('/api/library/tracks/rerun-parse-path?path=/music/b.mp3', headers=self.headers)
        self.assertEqual(response.json()['status'], 'ok')
        helper.return_value.mark_for_rescan.assert_called_once_with('/music/b.mp3', reason='rerun_parse')
        tagger.tag_single.assert_called_once_with('/music/b.mp3')
        scanner.scan_single.assert_called_once_with('/music/b.mp3')

    def test_a_failing_retag_by_path_is_still_reported_as_accepted(self):
        with (
            patch.object(library_router, 'ProcessedFilesHelper'),
            patch('services.music_manager.routers.tagger.tagger_manager') as tagger,
        ):
            tagger.tag_single.side_effect = RuntimeError('tagger busy')
            response = self.client.post('/api/library/tracks/rerun-parse-path?path=/music/b.mp3', headers=self.headers)
        self.assertEqual(response.status_code, 200)


class RedownloadTest(RouterTestCase):
    module = library_router

    def setUp(self):
        super().setUp()
        # TestClient runs background tasks inline; the real task would reach for yt-dlp.
        patcher = patch.object(library_router, 'run_redownload_task')
        self.redownload_task = patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_soundcloud_track_is_queued_for_redownload(self):
        self.cursor.fetchone.return_value = {'file_path': '/music/a.mp3'}
        self.cursor.fetchall.side_effect = [[{'url': 'https://soundcloud.com/x/y', 'stored': '/music/a.mp3'}]]
        response = self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.assertIn('soundcloud', response.json()['message'])

    def test_a_youtube_track_is_queued_when_soundcloud_has_nothing(self):
        self.cursor.fetchone.return_value = {'file_path': '/music/a.mp3'}
        self.cursor.fetchall.side_effect = [[], [{'url': 'https://youtube.com/watch?v=x', 'stored': '/music/a.mp3'}]]
        response = self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.assertIn('youtube', response.json()['message'])

    def test_a_track_without_a_source_url_cannot_be_redownloaded(self):
        self.cursor.fetchone.return_value = {'file_path': '/music/a.mp3'}
        self.cursor.fetchall.side_effect = [[], [], [], []]
        response = self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_a_track_without_a_file_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        response = self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_the_source_is_found_by_the_exact_stored_path_not_a_substring(self):
        # `filename LIKE '%name%' LIMIT 1` downloaded 'DJ Intro.mp3' over 'Intro.mp3'.
        self.cursor.fetchone.return_value = {'file_path': '/mnt/music/Soundcloud/x/Intro.mp3'}
        self.cursor.fetchall.side_effect = [
            [{'url': 'https://soundcloud.com/x/intro', 'stored': '/mnt/music/Soundcloud/x/Intro.mp3'}]
        ]
        self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        lookup, args = self.cursor.execute.call_args_list[1].args
        self.assertIn('WHERE filename IN (', lookup)
        self.assertNotIn('LIKE', lookup)
        self.assertIn('/mnt/music/Soundcloud/x/Intro.mp3', args)

    def test_a_stored_path_that_differs_only_in_case_is_not_this_file(self):
        # IN runs under the archive's case-insensitive collation.
        self.cursor.fetchone.return_value = {'file_path': '/music/a.mp3'}
        self.cursor.fetchall.side_effect = [[{'url': 'twin', 'stored': '/music/A.mp3'}], [], [], []]
        response = self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_the_youtube_archive_is_matched_on_its_path_column(self):
        self.cursor.fetchone.return_value = {'file_path': '/mnt/music/Youtube/x/a.m4a'}
        self.cursor.fetchall.side_effect = [[], [{'url': 'yt', 'stored': '/mnt/music/Youtube/x/a.m4a'}]]
        self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.assertIn('FROM downloads_youtube_archive WHERE path IN (', self.statements()[2])

    def test_the_library_file_is_handed_to_the_task_to_replace(self):
        self.cursor.fetchone.return_value = {'file_path': '/music/a.mp3'}
        self.cursor.fetchall.side_effect = [[{'url': 'https://soundcloud.com/x/y', 'stored': '/music/a.mp3'}]]
        self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.redownload_task.assert_called_once_with('https://soundcloud.com/x/y', 'soundcloud', '/music/a.mp3')

    def fallback(self, soundcloud_rows, youtube_rows, path='/mnt/music/Youtube/Channel/Intro_1.m4a'):
        """No stored path matched; the name-only lookups answer with these rows."""
        self.cursor.fetchone.return_value = {'file_path': path}
        self.cursor.fetchall.side_effect = [[], [], soundcloud_rows, youtube_rows]
        return self.client.post('/api/library/tracks/1/redownload', headers=self.headers)

    def test_the_name_only_lookup_takes_the_name_literally(self):
        self.fallback([], [{'url': 'yt', 'stored': 'Intro_1.m4a'}])
        soundcloud_query, args = self.cursor.execute.call_args_list[3].args
        self.assertIn('filename = %s OR filename LIKE %s', soundcloud_query)
        self.assertEqual(args, ('Intro_1.m4a', r'%/Intro\_1.m4a'))

    def test_a_row_that_never_recorded_a_folder_is_matched_by_name(self):
        response = self.fallback([], [{'url': 'yt', 'stored': 'Intro_1.m4a'}])
        self.assertEqual(response.status_code, 200)
        self.redownload_task.assert_called_once_with('yt', 'youtube', '/mnt/music/Youtube/Channel/Intro_1.m4a')

    def test_a_row_in_another_folder_is_not_this_file(self):
        response = self.fallback([], [{'url': 'yt', 'stored': '/music/Youtube/Other/Intro_1.m4a'}])
        self.assertEqual(response.status_code, 400)

    def test_a_row_that_differs_only_in_case_is_not_this_file(self):
        response = self.fallback([], [{'url': 'yt', 'stored': '/music/Youtube/Channel/intro_1.m4a'}])
        self.assertEqual(response.status_code, 400)

    def test_two_sources_for_one_name_are_refused_rather_than_guessed(self):
        response = self.fallback(
            [{'url': 'sc', 'stored': 'Intro_1.m4a'}], [{'url': 'yt', 'stored': '/x/Channel/Intro_1.m4a'}]
        )
        self.assertEqual(response.status_code, 409)
        self.redownload_task.assert_not_called()


class RedownloadTaskTest(unittest.TestCase):
    def test_a_soundcloud_redownload_uses_the_soundcloud_downloader(self):
        downloader_module = MagicMock()
        with patch.dict(sys.modules, {'services.downloader.soundcloud.soundcloud': downloader_module}):
            library_router.run_redownload_task('https://soundcloud.com/x', 'soundcloud')
        downloader = downloader_module.SoundcloudDownloader.return_value
        downloader.download_url.assert_called_once()
        self.assertTrue(downloader.redownload_mode)

    def test_a_youtube_redownload_uses_the_youtube_downloader(self):
        downloader_module = MagicMock()
        with patch.dict(sys.modules, {'services.downloader.youtube.youtube': downloader_module}):
            library_router.run_redownload_task('https://youtube.com/x', 'youtube')
        downloader_module.YoutubeDownloader.return_value.download_link.assert_called_once()

    def test_the_file_to_replace_reaches_both_downloaders(self):
        downloader_module = MagicMock()
        with (
            patch.dict(
                sys.modules,
                {
                    'services.downloader.youtube.youtube': downloader_module,
                    'services.downloader.soundcloud.soundcloud': downloader_module,
                },
            ),
            patch.object(library_router, 'ProcessedFilesHelper'),
        ):
            library_router.run_redownload_task('https://youtube.com/x', 'youtube', '/music/a.m4a')
            library_router.run_redownload_task('https://soundcloud.com/x', 'soundcloud', '/music/b.mp3')
        youtube_call = downloader_module.YoutubeDownloader.return_value.download_link.call_args
        self.assertEqual(youtube_call.kwargs['replace'], '/music/a.m4a')
        self.assertIs(youtube_call.kwargs['redownload'], True)
        soundcloud_call = downloader_module.SoundcloudDownloader.return_value.download_url.call_args
        self.assertEqual(soundcloud_call.kwargs['replace'], '/music/b.mp3')

    def test_the_replaced_file_is_queued_for_the_tagger(self):
        downloader_module = MagicMock()
        with (
            patch.dict(sys.modules, {'services.downloader.youtube.youtube': downloader_module}),
            patch.object(library_router, 'ProcessedFilesHelper') as helper,
            patch.object(library_router.os.path, 'exists', return_value=True),
        ):
            library_router.run_redownload_task('https://youtube.com/x', 'youtube', '/music/a.m4a')
        helper.return_value.mark_for_rescan.assert_called_once_with('/music/a.m4a', reason='redownload')

    def test_an_unknown_source_type_does_nothing(self):
        library_router.run_redownload_task('https://example.test/x', 'bandcamp')  # must not raise

    def test_a_failing_redownload_is_logged_rather_than_raised(self):
        downloader_module = MagicMock()
        downloader_module.SoundcloudDownloader.side_effect = RuntimeError('yt-dlp missing')
        with patch.dict(sys.modules, {'services.downloader.soundcloud.soundcloud': downloader_module}):
            library_router.run_redownload_task('https://soundcloud.com/x', 'soundcloud')  # must not raise


class ScrobbleEventTest(RouterTestCase):
    module = scrobbler_router

    def test_a_listen_for_a_known_track_is_stored_against_that_track(self):
        self.cursor.fetchone.return_value = {'id': 42}
        payload = {'artist_name': 'Angerfist', 'track_title': 'Raise Your Fist', 'username': 'user'}
        response = self.client.post('/api/scrobble/event', headers=self.headers, json=payload)
        self.assertTrue(response.json()['matched'])
        # Any statement, not a fixed index: the match ladder runs several
        # lookups before the insert, and how many depends on which tier hits.
        self.assertTrue(any('INSERT INTO scrobble_listens' in s for s in self.statements()))

    def test_a_listen_for_an_unknown_track_is_parked_as_unmatched(self):
        self.cursor.fetchone.return_value = None
        payload = {'artist_name': 'Nobody', 'track_title': 'Nothing', 'username': 'user'}
        response = self.client.post('/api/scrobble/event', headers=self.headers, json=payload)
        self.assertFalse(response.json()['matched'])
        self.assertTrue(any('scrobble_unmatched_listens' in s for s in self.statements()))

    def test_a_supplied_timestamp_is_used(self):
        self.cursor.fetchone.return_value = {'id': 42}
        payload = {'artist_name': 'A', 'track_title': 'B', 'username': 'user', 'listened_at': 1_700_000_000}
        self.client.post('/api/scrobble/event', headers=self.headers, json=payload)
        stored = self.cursor.execute.call_args.args[1][1]
        self.assertEqual(stored.year, 2023)

    def test_a_database_outage_is_reported_as_a_server_error(self):
        with patch.object(scrobbler_router, 'get_db_connection', return_value=None):
            payload = {'artist_name': 'A', 'track_title': 'B', 'username': 'user'}
            response = self.client.post('/api/scrobble/event', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 500)


class ListenBrainzImportTest(RouterTestCase):
    module = scrobbler_router

    def setUp(self):
        super().setUp()
        # TestClient runs background tasks inline; the real import would call ListenBrainz.
        patcher = patch.object(scrobbler_router, 'run_listenbrainz_import')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_latest_imports_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'status': 'completed'}]
        response = self.client.get('/api/scrobble/import/latest', headers=self.headers)
        self.assertEqual(response.json()[0]['status'], 'completed')

    def test_an_import_is_registered_and_queued(self):
        self.cursor.lastrowid = 7
        response = self.client.post(
            '/api/scrobble/import/listenbrainz',
            headers=self.headers,
            json={'username': 'user', 'lb_username': 'user-lb'},
        )
        self.assertEqual(response.json()['import_id'], 7)
        self.assertEqual(response.json()['lb_username'], 'user-lb')

    def test_without_a_listenbrainz_name_the_local_username_is_used(self):
        self.cursor.lastrowid = 8
        response = self.client.post(
            '/api/scrobble/import/listenbrainz', headers=self.headers, json={'username': 'user'}
        )
        self.assertEqual(response.json()['lb_username'], 'user')

    def _as_user(self, username, role_name='user'):
        """verify_token resolving the request's key to an ordinary (or admin) account."""
        return patch.object(
            users_router,
            'verify_token',
            return_value={'status': 'ok', 'type': 'user', 'user': {'username': username, 'role_name': role_name}},
        )

    def test_an_account_may_import_into_its_own_history(self):
        self.cursor.lastrowid = 9
        with self._as_user('user'):
            response = self.client.post(
                '/api/scrobble/import/listenbrainz', headers={'x-api-key': 'user-key'}, json={'username': 'user'}
            )
        self.assertEqual(response.status_code, 200)

    def test_an_account_may_not_import_into_someone_elses_history(self):
        with self._as_user('mallory'):
            response = self.client.post(
                '/api/scrobble/import/listenbrainz', headers={'x-api-key': 'user-key'}, json={'username': 'user'}
            )
        self.assertEqual(response.status_code, 403)
        self.cursor.execute.assert_not_called()

    def test_an_admin_may_import_for_anyone(self):
        self.cursor.lastrowid = 10
        with self._as_user('root', role_name='admin'):
            response = self.client.post(
                '/api/scrobble/import/listenbrainz', headers={'x-api-key': 'user-key'}, json={'username': 'user'}
            )
        self.assertEqual(response.status_code, 200)

    def test_the_management_proxy_applies_the_same_check(self):
        # Registered on the same path after the scrobbler router, so called directly here.
        from fastapi import HTTPException

        from services.music_manager.routers import management as management_router

        mallory = {'type': 'user', 'user': {'username': 'mallory', 'role_name': 'user'}}
        with self.assertRaises(HTTPException) as refused:
            management_router.trigger_lb_import_proxy(MagicMock(), {'username': 'user'}, mallory)
        self.assertEqual(refused.exception.status_code, 403)


class ProcessListensPageTest(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False

    def listen(self, artist='Angerfist', title='Raise Your Fist', ts=1_700_000_000):
        return {
            'track_metadata': {'artist_name': artist, 'track_name': title, 'release_name': 'Album'},
            'listened_at': ts,
        }

    def test_a_matched_listen_is_stored_against_the_track(self):
        self.cursor.fetchone.return_value = {'id': 42}
        processed, max_ts = scrobbler_router._process_listens_page([self.listen()], self.conn, 'user', 1, 1)
        self.assertEqual(processed, 1)
        self.assertEqual(max_ts, 1_700_000_000)
        self.assertTrue(
            any('INSERT INTO scrobble_listens' in call.args[0] for call in self.cursor.execute.call_args_list)
        )

    def test_an_unmatched_listen_is_parked(self):
        self.cursor.fetchone.return_value = None
        scrobbler_router._process_listens_page([self.listen()], self.conn, 'user', 1, 1)
        self.assertTrue(
            any('scrobble_unmatched_listens' in call.args[0] for call in self.cursor.execute.call_args_list)
        )

    def test_an_incomplete_listen_is_skipped(self):
        self.cursor.fetchone.return_value = {'id': 42}
        processed, _ = scrobbler_router._process_listens_page(
            [self.listen(artist=None), self.listen(title=None)], self.conn, 'user', 1, 2
        )
        self.assertEqual(processed, 0)

    def test_the_oldest_timestamp_of_the_page_is_returned_for_paging(self):
        self.cursor.fetchone.return_value = {'id': 42}
        _, max_ts = scrobbler_router._process_listens_page(
            [self.listen(ts=200), self.listen(ts=100)], self.conn, 'user', 1, 2
        )
        self.assertEqual(max_ts, 100)

    def test_a_listen_without_a_timestamp_does_not_break_the_page(self):
        # The comparison ran before the None check: a timestamp-less listen after the first
        # one raised TypeError and failed the whole import.
        self.cursor.fetchone.return_value = {'id': 42}
        processed, oldest = scrobbler_router._process_listens_page(
            [self.listen(ts=200), self.listen(ts=None), self.listen(ts=100)], self.conn, 'user', 1, 3
        )
        self.assertEqual(processed, 2)
        self.assertEqual(oldest, 100)

    def test_a_page_with_no_timestamps_has_no_oldest(self):
        _, oldest = scrobbler_router._process_listens_page([self.listen(ts=None)], self.conn, 'user', 1, 1)
        self.assertIsNone(oldest)

    def test_progress_is_written_back_every_ten_listens(self):
        self.cursor.fetchone.return_value = {'id': 42}
        listens = [self.listen(ts=1000 - i) for i in range(10)]
        scrobbler_router._process_listens_page(listens, self.conn, 'user', 1, 10)
        progress_updates = [call for call in self.cursor.execute.call_args_list if 'SET processed' in call.args[0]]
        self.assertEqual(len(progress_updates), 1)


class RunListenBrainzImportTest(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patches = [
            patch.object(scrobbler_router, 'get_db_connection', return_value=self.conn),
            patch.object(scrobbler_router.time, 'sleep'),
            patch('builtins.print'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def page(self, count):
        return {
            'payload': {
                'listens': [
                    {'track_metadata': {'artist_name': 'A', 'track_name': 'B'}, 'listened_at': 1_700_000_000 - i}
                    for i in range(count)
                ]
            }
        }

    def test_an_import_that_finds_nothing_is_still_marked_completed(self):
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.return_value = {'payload': {'listens': []}}
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        self.assertEqual(self.statuses()[-1], 'completed')

    def test_a_short_page_ends_the_import(self):
        self.cursor.fetchone.return_value = {'id': 42}
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.return_value = self.page(3)
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        self.assertEqual(http.get.call_count, 1)

    def test_a_full_page_is_followed_by_another_request(self):
        self.cursor.fetchone.return_value = {'id': 42}
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.side_effect = [self.page(100), {'payload': {'listens': []}}]
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        self.assertEqual(http.get.call_count, 2)

    def test_a_token_is_sent_as_an_authorization_header(self):
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.return_value = {'payload': {'listens': []}}
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb', token='tok')
        self.assertEqual(http.get.call_args.kwargs['headers'], {'Authorization': 'Token tok'})

    def test_a_failing_import_is_recorded_as_failed(self):
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.side_effect = RuntimeError('listenbrainz down')
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        self.assertTrue(any("status = 'failed'" in call.args[0] for call in self.cursor.execute.call_args_list))

    def statuses(self):
        """Every status the run wrote to its import row, in order."""
        found = []
        for call in self.cursor.execute.call_args_list:
            sql = call.args[0]
            if "status = 'running'" in sql:
                found.append('running')
            elif "status = 'failed'" in sql:
                found.append('failed')
            elif 'SET status = %s' in sql:
                found.append(call.args[1][0])
        return found

    def test_the_next_page_starts_strictly_below_the_oldest_listen_seen(self):
        # max_ts is exclusive on ListenBrainz; max_ts - 1 skipped listens at that second.
        self.cursor.fetchone.return_value = {'id': 42}
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.side_effect = [self.page(100), {'payload': {'listens': []}}]
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        oldest_on_first_page = 1_700_000_000 - 99
        self.assertEqual(http.get.call_args_list[1].kwargs['params']['max_ts'], oldest_on_first_page)
        self.assertEqual(self.statuses(), ['running', 'completed'])

    def test_hitting_the_page_cap_is_reported_as_truncated(self):
        self.cursor.fetchone.return_value = {'id': 42}
        pages = [
            {
                'payload': {
                    'listens': [
                        {'track_metadata': {'artist_name': 'A', 'track_name': 'B'}, 'listened_at': 10_000 - p * 100 - i}
                        for i in range(scrobbler_router.LB_PAGE_SIZE)
                    ]
                }
            }
            for p in range(3)
        ]
        with (
            patch.object(scrobbler_router, 'LB_MAX_PAGES', 3),
            patch.object(scrobbler_router, 'requests') as http,
        ):
            http.get.return_value.json.side_effect = pages
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        self.assertEqual(http.get.call_count, 3)
        self.assertEqual(self.statuses(), ['running', 'truncated'])
        resume_writes = [
            call.args[1] for call in self.cursor.execute.call_args_list if 'SET oldest_listened_ts = %s' in call.args[0]
        ]
        self.assertEqual(resume_writes[-1], (10_000 - 299, 1))

    def test_an_import_continues_below_a_truncated_predecessor(self):
        self.cursor.fetchone.return_value = {'status': 'truncated', 'oldest_listened_ts': 1_600_000_000}
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.return_value = {'payload': {'listens': []}}
            scrobbler_router.run_listenbrainz_import(2, 'user', 'user-lb')
        self.assertEqual(http.get.call_args.kwargs['params']['max_ts'], 1_600_000_000)
        lookup = self.cursor.execute.call_args_list[0].args
        self.assertIn('FROM scrobble_imports', lookup[0])
        self.assertEqual(lookup[1], ('user', 'user-lb', 2))

    def test_an_import_after_a_completed_one_starts_at_the_newest_listen(self):
        self.cursor.fetchone.return_value = {'status': 'completed', 'oldest_listened_ts': 1_600_000_000}
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.return_value = {'payload': {'listens': []}}
            scrobbler_router.run_listenbrainz_import(2, 'user', 'user-lb')
        self.assertNotIn('max_ts', http.get.call_args.kwargs['params'])

    def test_a_page_that_cannot_advance_ends_the_import(self):
        # A full page without timestamps would otherwise be fetched again forever.
        page = {
            'payload': {
                'listens': [
                    {'track_metadata': {'artist_name': 'A', 'track_name': 'B'}, 'listened_at': None}
                    for _ in range(scrobbler_router.LB_PAGE_SIZE)
                ]
            }
        }
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.return_value = page
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        self.assertEqual(http.get.call_count, 1)
        self.assertEqual(self.statuses(), ['running', 'completed'])

    def test_an_import_without_a_database_connection_ends_immediately(self):
        with (
            patch.object(scrobbler_router, 'get_db_connection', return_value=None),
            patch.object(scrobbler_router, 'requests') as http,
        ):
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        http.get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
