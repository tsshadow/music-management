import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users
from services.music_manager.api_key import resolve_system_api_key

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from fastapi.testclient import TestClient

from services.music_manager.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_real_config_store(config_path: str):
    """Import the real ConfigStore, bypassing the session-wide mock.

    services/conftest.py replaces services.common.config_store with a MagicMock for
    the whole test session, which would happily accept a call to a method that does
    not exist. These tests need the real thing.
    """
    os.environ['CONFIG_PATH'] = config_path
    spec = importlib.util.spec_from_file_location(
        'real_config_store', REPO_ROOT / 'services' / 'common' / 'config_store.py')
    module = importlib.util.module_from_spec(spec)
    # dataclass() looks the defining module up in sys.modules while the class body
    # is executed, so it has to be registered before the module is run.
    sys.modules['real_config_store'] = module
    spec.loader.exec_module(module)
    module.ConfigStore._instance = None
    module.ConfigStore._initialized = False
    return module.ConfigStore()


class ConfigEndpointTest(unittest.TestCase):
    """The settings endpoint has to actually write through to the store."""

    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()
        self.headers = {'x-api-key': self.api_key}
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = load_real_config_store(os.path.join(self.tempdir.name, 'config.json'))
        patch('services.music_manager.routers.config.config_store', self.store).start()

    def tearDown(self):
        patch.stopall()
        self.tempdir.cleanup()
        os.environ.pop('CONFIG_PATH', None)

    def test_saving_a_setting_reports_success(self):
        response = self.client.post('/api/config/', headers=self.headers,
                                    json={'updates': {'notify_topic': 'music-alerts'}})
        self.assertEqual(response.status_code, 200)

    def test_saving_a_setting_actually_changes_it(self):
        self.client.post('/api/config/', headers=self.headers,
                         json={'updates': {'notify_topic': 'music-alerts'}})
        self.assertEqual(self.store.get('notify_topic'), 'music-alerts')

    def test_the_new_value_is_readable_over_the_api(self):
        self.client.post('/api/config/', headers=self.headers,
                         json={'updates': {'notify_topic': 'music-alerts'}})
        body = self.client.get('/api/config/', headers=self.headers).json()
        self.assertEqual(body['config']['notify_topic'], 'music-alerts')

    def test_an_unknown_key_is_refused(self):
        response = self.client.post('/api/config/', headers=self.headers,
                                    json={'updates': {'nonsense_key': 'x'}})
        self.assertEqual(response.status_code, 400)

    def test_saving_needs_a_key(self):
        response = self.client.post('/api/config/', json={'updates': {'notify_topic': 'x'}})
        self.assertEqual(response.status_code, 401)


class ConfigPermissionTest(ConfigEndpointTest):
    """Reading the configuration is an admin act, not something any session may do.

    It used to hang on `verify_api_key` alone, so any logged-in user could fetch the
    database password and every third-party token in the clear.
    """

    def _as_plain_user(self):
        return patch.object(
            services.music_manager.routers.users, 'verify_token',
            return_value={'status': 'ok', 'type': 'user',
                          'user': {'username': 'user', 'role_name': 'user',
                                   'permissions': ['music.read']}})

    def test_a_plain_user_may_not_read_the_configuration(self):
        with self._as_plain_user():
            response = self.client.get('/api/config/', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 403)

    def test_a_plain_user_may_not_read_the_schema(self):
        with self._as_plain_user():
            response = self.client.get('/api/config/fields', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 403)

    def test_a_plain_user_may_not_write_the_configuration(self):
        with self._as_plain_user():
            response = self.client.post('/api/config/', headers={'x-api-key': 'user-key'},
                                        json={'updates': {'notify_topic': 'x'}})
        self.assertEqual(response.status_code, 403)

    def test_reading_the_schema_still_needs_a_key(self):
        self.assertEqual(self.client.get('/api/config/fields').status_code, 401)


class ConfigSecretTest(ConfigEndpointTest):
    """Secrets are masked on the way out and preserved on the way back in."""

    def test_a_stored_secret_does_not_leave_over_the_api(self):
        self.store.update({'db_pass': 'hunter2'})
        body = self.client.get('/api/config/', headers=self.headers).json()
        self.assertNotEqual(body['config']['db_pass'], 'hunter2')

    def test_the_schema_marks_which_fields_are_secret(self):
        fields = {row['key']: row for row in self.client.get('/api/config/fields',
                                                             headers=self.headers).json()}
        self.assertTrue(fields['db_pass']['secret'])
        self.assertFalse(fields['db_user']['secret'])
        # An identifier is not a credential: the Spotify client id is public.
        self.assertFalse(fields['spotify_client_id']['secret'])
        self.assertTrue(fields['spotify_client_secret']['secret'])

    def test_posting_the_page_back_unchanged_keeps_the_secret(self):
        self.store.update({'db_pass': 'hunter2'})
        page = self.client.get('/api/config/', headers=self.headers).json()['config']
        page['notify_topic'] = 'something-else'
        self.client.post('/api/config/', headers=self.headers, json={'updates': page})
        self.assertEqual(self.store.get('db_pass'), 'hunter2')
        self.assertEqual(self.store.get('notify_topic'), 'something-else')

    def test_a_deliberately_typed_secret_is_stored(self):
        self.client.post('/api/config/', headers=self.headers,
                         json={'updates': {'db_pass': 'correct horse'}})
        self.assertEqual(self.store.get('db_pass'), 'correct horse')


class ConfigRetagLimitTest(ConfigEndpointTest):
    """The curation retag ceiling is read from the configuration, not hardcoded."""

    def test_the_ceiling_is_exposed_as_a_tagger_setting(self):
        fields = {row['key']: row for row in self.client.get('/api/config/fields',
                                                             headers=self.headers).json()}
        self.assertEqual(fields['max_retag_files']['group'], 'Tagger')
        self.assertEqual(fields['max_retag_files']['default'], 2000)

    def test_the_ceiling_can_be_lowered(self):
        response = self.client.post('/api/config/', headers=self.headers,
                                    json={'updates': {'max_retag_files': 50}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.get('max_retag_files'), 50)


if __name__ == '__main__':
    unittest.main()
