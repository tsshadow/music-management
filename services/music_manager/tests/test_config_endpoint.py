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
        self.api_key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'
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


if __name__ == '__main__':
    unittest.main()
