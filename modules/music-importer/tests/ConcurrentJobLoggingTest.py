import os
import sys
import time
import types
import unittest
import importlib
import logging

from fastapi.testclient import TestClient

# Minimal env vars for Settings
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
                attrs = {
                    '__init__': lambda self, *a, **k: None,
                    'run': lambda self, *a, **k: logging.info(message) or time.sleep(0.1) if message else None,
                }
                if module_name == 'downloader.youtube' and cls == 'YoutubeDownloader':
                    attrs['download_link'] = lambda self, *a, **k: None
                mod_class = type(cls, (), attrs)
                setattr(mod, cls, mod_class)
            return mod

        modules_to_stub = {
            'downloader.youtube': {'YoutubeDownloader': None},
            'downloader.soundcloud': {'SoundcloudDownloader': 'download job log'},
            'downloader.telegram': {'TelegramDownloader': None},
            'processing.converter': {'Converter': None},
            'processing.epsflattener': {'EpsFlattener': None},
            'processing.extractor': {'Extractor': None},
            'processing.mover': {'Mover': None},
            'processing.renamer': {'Renamer': None},
            'postprocessing.sanitizer': {'Sanitizer': None},
            'postprocessing.analyze': {'Analyze': None},
            'postprocessing.artistfixer': {'ArtistFixer': None},
            'postprocessing.tagger': {'Tagger': 'tag job log'},
        }

        for mod_name, classes in modules_to_stub.items():
            self.original_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = _make_stub_module(mod_name, classes)

        # stub out DB initialization to avoid real connections
        import api.db_init as db_init
        self._orig_ensure_tables = db_init.ensure_tables_exist
        db_init.ensure_tables_exist = lambda: None

        # provide minimal main module exposing Step
        from step import Step as RealStep
        self.original_modules['main'] = sys.modules.get('main')
        main_mod = types.ModuleType('main')
        main_mod.Step = RealStep
        sys.modules['main'] = main_mod

        import api.server as server_module
        self.server = importlib.reload(server_module)
        self.server.jobs.clear()

    def tearDown(self):
        import api.db_init as db_init
        db_init.ensure_tables_exist = self._orig_ensure_tables
        for name, mod in self.original_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def test_logs_are_isolated(self):
        with TestClient(self.server.app) as client:
            tag_job = client.post('/api/run/tag').json()
            dl_job = client.post('/api/run/download').json()

        # Wait for jobs to finish
        time.sleep(0.3)

        tag_log = self.server.jobs[tag_job['id']]['log']
        dl_log = self.server.jobs[dl_job['id']]['log']

        self.assertTrue(any('tag job log' in line for line in tag_log))
        self.assertFalse(any('download job log' in line for line in tag_log))
        self.assertTrue(any('download job log' in line for line in dl_log))
        self.assertFalse(any('tag job log' in line for line in dl_log))


if __name__ == '__main__':
    unittest.main()
