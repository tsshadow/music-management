import os
import sys
import time
import types
import unittest
import importlib
import logging
from fastapi.testclient import TestClient

from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
from services.downloader.telegram.telegram import TelegramDownloader
from services.downloader.youtube.youtube import YoutubeDownloader

os.environ.setdefault('import_folder_path', '/tmp')
os.environ.setdefault('music_folder_path', '/tmp')
os.environ.setdefault('eps_folder_path', '/tmp')
os.environ.setdefault('delimiter', '/')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_USER', 'user')
os.environ.setdefault('DB_PORT', '0')
os.environ.setdefault('DB_PASS', '')
os.environ.setdefault('DB_DB', 'db')

class ConcurrentJobLoggingTest(unittest.TestCase):

    def setUp(self):
        self.original_modules = {}

        def _make_stub_module(module_name, class_names):
            mod = types.ModuleType(module_name)
            for cls, message in class_names.items():
                attrs = {'__init__': lambda self, *a, **k: None, 'run': lambda self, *a, **k: logging.info(message) or time.sleep(0.1) if message else None}
                if module_name == 'services.downloader.youtube.youtube' and cls == 'YoutubeDownloader':
                    attrs['download_link'] = lambda self, *a, **k: None
                mod_class = type(cls, (), attrs)
                setattr(mod, cls, mod_class)
            return mod
        modules_to_stub = {
            'services.downloader.youtube.youtube': {'YoutubeDownloader': None},
            'services.downloader.soundcloud.soundcloud': {'SoundcloudDownloader': 'download job log'},
            'services.downloader.telegram.telegram': {'TelegramDownloader': None},
            'services.tagger.tagger': {'Tagger': 'tag job log'}
        }
        for mod_name, classes in modules_to_stub.items():
            self.original_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = _make_stub_module(mod_name, classes)
        
        import services.common.api.run_tagger as run_tagger_mod
        importlib.reload(run_tagger_mod)
        import services.common.api.steps as steps_mod
        importlib.reload(steps_mod)
        import services.common.api.server as server_module
        self.server = importlib.reload(server_module)
        self.server.jobs.clear()
        
        import services.common.api.db_init as db_init
        self._orig_ensure_tables = db_init.ensure_tables_exist
        db_init.ensure_tables_exist = lambda: None

    def tearDown(self):
        import services.common.api.db_init as db_init
        db_init.ensure_tables_exist = self._orig_ensure_tables
        for name, mod in self.original_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def test_logs_are_isolated(self):
        with TestClient(self.server.app) as client:
            tag_job = client.post('/api/run/tag').json()
            dl_job = client.post('/api/run/soundcloud').json()
        time.sleep(0.3)
        tag_log = self.server.jobs[tag_job['id']].get('log', [])
        dl_log = self.server.jobs[dl_job['id']].get('log', [])
        self.assertTrue(any(('tag job log' in line for line in tag_log)))
        self.assertFalse(any(('download job log' in line for line in tag_log)))
        self.assertTrue(any(('download job log' in line for line in dl_log)))
        self.assertFalse(any(('tag job log' in line for line in dl_log)))
if __name__ == '__main__':
    unittest.main()