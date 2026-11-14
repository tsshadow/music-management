import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

# Only stub these when they aren't already provided by services/tests/mock_base.py

import services.music_manager.routers.users
from services.music_manager.api_key import resolve_system_api_key

services.music_manager.routers.users.run_lms_db_sync = lambda only_sources=None: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from fastapi.testclient import TestClient

from services.downloader.rate_state import InMemoryRateStateStore, RateState
from services.downloader.settings_store import InMemorySettingsStore
from services.downloader.timing import load_timing
from services.music_manager.main import app

NOW = datetime(2026, 7, 30, 12, 0, 0)


class DownloaderApiTestBase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()
        self.headers = {'x-api-key': self.api_key}
        self.settings_store = InMemorySettingsStore()
        self.rate_store = InMemoryRateStateStore()
        patch('services.music_manager.routers.downloaders.settings_store', self.settings_store).start()
        patch('services.music_manager.routers.downloaders.rate_state_store', self.rate_store).start()

    def tearDown(self):
        patch.stopall()


class SettingsEndpointTest(DownloaderApiTestBase):
    def test_the_schema_lists_every_source(self):
        body = self.client.get('/api/downloaders/settings', headers=self.headers).json()
        self.assertEqual({entry['source'] for entry in body['sources']}, {'soundcloud', 'youtube', 'telegram'})

    def test_a_field_carries_everything_the_ui_needs_to_render_it(self):
        body = self.client.get('/api/downloaders/settings', headers=self.headers).json()
        soundcloud = next(entry for entry in body['sources'] if entry['source'] == 'soundcloud')
        sweep = next(field for field in soundcloud['fields'] if field['key'] == 'sweep_interval')
        self.assertEqual(set(sweep), {'key', 'value', 'default', 'minimum', 'maximum', 'unit', 'description'})

    def test_an_unset_field_reports_its_default_as_the_value(self):
        body = self.client.get('/api/downloaders/settings', headers=self.headers).json()
        soundcloud = next(entry for entry in body['sources'] if entry['source'] == 'soundcloud')
        sweep = next(field for field in soundcloud['fields'] if field['key'] == 'sweep_interval')
        self.assertEqual(sweep['value'], sweep['default'])

    def test_a_saved_value_shows_up_on_the_next_read(self):
        self.client.post(
            '/api/downloaders/settings',
            headers=self.headers,
            json={'source': 'soundcloud', 'updates': {'sweep_interval': 4200}},
        )
        body = self.client.get('/api/downloaders/settings', headers=self.headers).json()
        soundcloud = next(entry for entry in body['sources'] if entry['source'] == 'soundcloud')
        sweep = next(field for field in soundcloud['fields'] if field['key'] == 'sweep_interval')
        self.assertEqual(sweep['value'], 4200)

    def test_saving_reports_what_was_stored(self):
        response = self.client.post(
            '/api/downloaders/settings',
            headers=self.headers,
            json={'source': 'soundcloud', 'updates': {'burst_size': 3}},
        )
        self.assertEqual(response.json()['updated'], {'burst_size': 3})

    def test_an_out_of_range_value_is_refused(self):
        response = self.client.post(
            '/api/downloaders/settings',
            headers=self.headers,
            json={'source': 'soundcloud', 'updates': {'max_workers': 0}},
        )
        self.assertEqual(response.status_code, 400)

    def test_an_unknown_knob_is_refused(self):
        response = self.client.post(
            '/api/downloaders/settings',
            headers=self.headers,
            json={'source': 'soundcloud', 'updates': {'nonsense_knob': 1}},
        )
        self.assertEqual(response.status_code, 400)

    def test_an_unknown_source_is_refused(self):
        response = self.client.post(
            '/api/downloaders/settings', headers=self.headers, json={'source': 'bandcamp', 'updates': {'burst_size': 1}}
        )
        self.assertEqual(response.status_code, 400)

    def test_a_refused_save_stores_nothing(self):
        self.client.post(
            '/api/downloaders/settings',
            headers=self.headers,
            json={'source': 'soundcloud', 'updates': {'max_workers': 0}},
        )
        self.assertEqual(self.settings_store.load('soundcloud'), {})

    def test_reading_the_settings_needs_a_key(self):
        self.assertEqual(self.client.get('/api/downloaders/settings').status_code, 401)

    def test_writing_the_settings_needs_a_key(self):
        response = self.client.post(
            '/api/downloaders/settings', json={'source': 'soundcloud', 'updates': {'burst_size': 3}}
        )
        self.assertEqual(response.status_code, 401)


class BrokenStore:
    """A store whose database is unreachable."""

    def load(self, source):
        raise RuntimeError('Connection refused')

    def save(self, source, values):
        raise RuntimeError('Connection refused')


class UnreachableStorageTest(DownloaderApiTestBase):
    """A storage failure must be reported, never disguised as "everything is default".

    The worker deliberately falls back to the defaults so a downloader keeps running
    without the database. The UI must not inherit that: a screen full of defaults is
    indistinguishable from settings that were never saved, which is exactly the
    complaint this covers.
    """

    def setUp(self):
        super().setUp()
        patch('services.music_manager.routers.downloaders.settings_store', BrokenStore()).start()

    def test_reading_the_settings_reports_the_outage(self):
        response = self.client.get('/api/downloaders/settings', headers=self.headers)
        self.assertEqual(response.status_code, 503)

    def test_the_read_failure_says_what_went_wrong(self):
        response = self.client.get('/api/downloaders/settings', headers=self.headers)
        self.assertIn('Connection refused', response.json()['detail'])

    def test_writing_the_settings_reports_the_outage(self):
        response = self.client.post(
            '/api/downloaders/settings',
            headers=self.headers,
            json={'source': 'soundcloud', 'updates': {'burst_size': 3}},
        )
        self.assertEqual(response.status_code, 503)

    def test_the_write_failure_says_what_went_wrong(self):
        response = self.client.post(
            '/api/downloaders/settings',
            headers=self.headers,
            json={'source': 'soundcloud', 'updates': {'burst_size': 3}},
        )
        self.assertIn('Connection refused', response.json()['detail'])

    def test_an_invalid_value_is_still_a_400(self):
        response = self.client.post(
            '/api/downloaders/settings',
            headers=self.headers,
            json={'source': 'soundcloud', 'updates': {'max_workers': 0}},
        )
        self.assertEqual(response.status_code, 400)

    def test_the_rate_state_reports_the_outage_too(self):
        response = self.client.get('/api/downloaders/rate-state', headers=self.headers)
        self.assertEqual(response.status_code, 503)


class RateStateEndpointTest(DownloaderApiTestBase):
    def _park_soundcloud(self):
        timing = load_timing('soundcloud', overrides={'backoff_429_base': 3600, 'max_multiplier': 16})
        state = RateState('soundcloud', timing, store=self.rate_store, now=lambda: NOW, jitter=lambda: 1.0)
        state.record_429()

    def test_a_quiet_source_reports_a_neutral_multiplier(self):
        body = self.client.get('/api/downloaders/rate-state', headers=self.headers).json()
        soundcloud = next(entry for entry in body['sources'] if entry['source'] == 'soundcloud')
        self.assertEqual(soundcloud['multiplier'], 1)

    def test_every_source_is_reported(self):
        body = self.client.get('/api/downloaders/rate-state', headers=self.headers).json()
        self.assertEqual({entry['source'] for entry in body['sources']}, {'soundcloud', 'youtube', 'telegram'})

    def test_a_parked_source_reports_its_multiplier(self):
        self._park_soundcloud()
        body = self.client.get('/api/downloaders/rate-state', headers=self.headers).json()
        soundcloud = next(entry for entry in body['sources'] if entry['source'] == 'soundcloud')
        self.assertEqual(soundcloud['multiplier'], 2)

    def test_a_parked_source_reports_when_it_wakes_up(self):
        self._park_soundcloud()
        body = self.client.get('/api/downloaders/rate-state', headers=self.headers).json()
        soundcloud = next(entry for entry in body['sources'] if entry['source'] == 'soundcloud')
        self.assertIsNotNone(soundcloud['cooldown_until'])

    def test_the_reported_interval_includes_the_multiplier(self):
        self._park_soundcloud()
        body = self.client.get('/api/downloaders/rate-state', headers=self.headers).json()
        soundcloud = next(entry for entry in body['sources'] if entry['source'] == 'soundcloud')
        base = load_timing('soundcloud', overrides={}).sweep_interval
        self.assertEqual(soundcloud['effective_sweep_interval'], base * 2)

    def test_resetting_clears_the_multiplier(self):
        self._park_soundcloud()
        self.client.post('/api/downloaders/rate-state/soundcloud/reset', headers=self.headers)
        body = self.client.get('/api/downloaders/rate-state', headers=self.headers).json()
        soundcloud = next(entry for entry in body['sources'] if entry['source'] == 'soundcloud')
        self.assertEqual(soundcloud['multiplier'], 1)

    def test_a_source_parked_on_the_bot_check_says_so(self):
        timing = load_timing('youtube', overrides={})
        RateState('youtube', timing, store=self.rate_store, now=lambda: NOW).record_block('bot_check', 21600)
        body = self.client.get('/api/downloaders/rate-state', headers=self.headers).json()
        youtube = next(entry for entry in body['sources'] if entry['source'] == 'youtube')
        self.assertEqual(youtube['block_reason'], 'bot_check')

    def test_a_plain_cooldown_has_no_block_reason(self):
        self._park_soundcloud()
        body = self.client.get('/api/downloaders/rate-state', headers=self.headers).json()
        soundcloud = next(entry for entry in body['sources'] if entry['source'] == 'soundcloud')
        self.assertIsNone(soundcloud['block_reason'])

    def test_resetting_clears_the_cooldown(self):
        self._park_soundcloud()
        self.client.post('/api/downloaders/rate-state/soundcloud/reset', headers=self.headers)
        body = self.client.get('/api/downloaders/rate-state', headers=self.headers).json()
        soundcloud = next(entry for entry in body['sources'] if entry['source'] == 'soundcloud')
        self.assertEqual(soundcloud['cooldown_remaining'], 0)

    def test_resetting_an_unknown_source_is_refused(self):
        response = self.client.post('/api/downloaders/rate-state/bandcamp/reset', headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_reading_the_rate_state_needs_a_key(self):
        self.assertEqual(self.client.get('/api/downloaders/rate-state').status_code, 401)

    def test_resetting_needs_a_key(self):
        self.assertEqual(self.client.post('/api/downloaders/rate-state/soundcloud/reset').status_code, 401)


if __name__ == '__main__':
    unittest.main()


class CoverageEndpointTest(DownloaderApiTestBase):
    """The page's one read, with the four queries and the check store swapped for canned data."""

    class Queries:
        def __init__(self, fail=False, channels_fail=False):
            self.fail = fail
            self.channels_fail = channels_fail

        def configured(self, source):
            if self.fail:
                raise RuntimeError('db down')
            from services.music_manager.downloader_coverage import ConfiguredAccount

            if source == 'youtube':
                return [ConfiguredAccount('@dj_a', '@dj_a#video', 'video')]
            return [ConfiguredAccount('dj_a', 'dj_a', archive_key='101'), ConfiguredAccount('dj_b', 'dj_b')]

        def archive_summary(self, source):
            return {'101': NOW}, {'101': '/mnt/music/Soundcloud/DJ A/track.mp3'}

        def channels(self, source):
            if self.channels_fail:
                raise RuntimeError('no proposals table')
            return {
                'dj a': {
                    'id': 7,
                    'name': 'DJ A',
                    'label': None,
                    'artist': {'id': 3, 'name': 'DJ A'},
                    'open_proposals': 1,
                }
            }

        def recent_downloads(self, source):
            return (3, 9)

        def write_offs(self, source):
            return {'too_short': 4}

    class Checks:
        def load(self, source):
            from services.downloader.account_schedule import AccountCheck
            from services.downloader.account_snapshot import AccountSnapshot

            snapshot = AccountSnapshot(100, 60, 10, 30, 'capped', NOW)
            return {'dj_a': AccountCheck(NOW, snapshot=snapshot), '@dj_a#video': AccountCheck(NOW, snapshot=snapshot)}

    def setUp(self):
        super().setUp()
        patch('services.music_manager.routers.downloaders.coverage_queries', self.Queries()).start()
        patch('services.music_manager.routers.downloaders.DatabaseCheckStore', self.Checks).start()

    def test_the_body_has_the_tiles_the_rows_and_the_backoff(self):
        body = self.client.get('/api/downloaders/coverage/soundcloud', headers=self.headers).json()
        self.assertEqual('soundcloud', body['source'])
        self.assertEqual(2, body['totals']['configured'])
        self.assertEqual(1, body['totals']['never_counted'])
        self.assertEqual(30, body['totals']['remaining'])
        self.assertEqual((3, 9), (body['totals']['downloads_7d'], body['totals']['downloads_30d']))
        self.assertEqual(4, body['totals']['write_offs'][0]['count'])
        self.assertEqual('soundcloud', body['totals']['rate_state']['source'])
        self.assertEqual(['dj_a', 'dj_b'], [row['account'] for row in body['accounts']])
        self.assertEqual(NOW.isoformat(), body['accounts'][0]['last_download_at'])

    def test_a_soundcloud_account_is_found_in_the_archive_by_its_numeric_id(self):
        """Bug report 089: the archive files rows under soundcloud_id, never under the slug."""
        body = self.client.get('/api/downloaders/coverage/soundcloud', headers=self.headers).json()
        rows = {row['account']: row for row in body['accounts']}
        self.assertEqual(NOW.isoformat(), rows['dj_a']['last_download_at'])
        self.assertIsNone(rows['dj_b']['last_download_at'])

    def test_an_account_carries_the_channel_its_files_are_filed_under(self):
        body = self.client.get('/api/downloaders/coverage/soundcloud', headers=self.headers).json()
        rows = {row['account']: row for row in body['accounts']}
        self.assertEqual({'id': 3, 'name': 'DJ A'}, rows['dj_a']['channel']['artist'])
        self.assertEqual(1, rows['dj_a']['channel']['open_proposals'])
        self.assertIsNone(rows['dj_b']['channel'])

    def test_a_failing_channel_read_leaves_the_counts_standing(self):
        patch('services.music_manager.routers.downloaders.coverage_queries', self.Queries(channels_fail=True)).start()
        response = self.client.get('/api/downloaders/coverage/soundcloud', headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertTrue(all(row['channel'] is None for row in response.json()['accounts']))

    def test_a_youtube_video_channel_is_matched_on_its_schedule_key(self):
        body = self.client.get('/api/downloaders/coverage/youtube', headers=self.headers).json()
        row = body['accounts'][0]
        self.assertEqual(('@dj_a', 'video', 100), (row['account'], row['download_type'], row['listed']))

    def test_an_unknown_source_is_refused(self):
        response = self.client.get('/api/downloaders/coverage/telegram', headers=self.headers)
        self.assertEqual(400, response.status_code)

    def test_a_database_outage_is_a_503_with_the_reason(self):
        patch('services.music_manager.routers.downloaders.coverage_queries', self.Queries(fail=True)).start()
        response = self.client.get('/api/downloaders/coverage/soundcloud', headers=self.headers)
        self.assertEqual(503, response.status_code)
        self.assertIn('db down', response.json()['detail'])

    def test_reading_the_coverage_needs_a_key(self):
        response = self.client.get('/api/downloaders/coverage/soundcloud')
        self.assertIn(response.status_code, (401, 403))
