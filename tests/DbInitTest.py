import os
import importlib
import unittest
import sys
import types
from unittest.mock import patch

from fastapi.testclient import TestClient

# minimal env vars
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_USER', 'user')
os.environ.setdefault('DB_PORT', '0')
os.environ.setdefault('DB_PASS', '')
os.environ.setdefault('DB_DB', 'db')
os.environ.setdefault('import_folder_path', '/tmp')
os.environ.setdefault('music_folder_path', '/tmp')
os.environ.setdefault('eps_folder_path', '/tmp')
os.environ.setdefault('delimiter', '/')


class DbInitTest(unittest.TestCase):
    def test_ensure_tables_exist_executes_create_statements(self):
        executed = []

        class DummyCursor:
            def execute(self, sql):
                executed.append(sql)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                pass

        class DummyConnection:
            def cursor(self):
                return DummyCursor()

            def commit(self):
                pass

            def close(self):
                pass

        with patch('api.db_init.DatabaseConnector.connect', return_value=DummyConnection()):
            from api.db_init import ensure_tables_exist
            ensure_tables_exist()

        self.assertEqual(len(executed), 4)
        joined = ' '.join(executed)
        self.assertIn('soundcloud_accounts', joined)
        self.assertIn('youtube_archive', joined)

    def test_server_startup_calls_ensure_tables_exist(self):
        original_modules = {}

        def _make_stub_module(module_name, class_names):
            mod = types.ModuleType(module_name)
            for cls in class_names:
                attrs = {
                    '__init__': lambda self, *a, **k: None,
                    'run': lambda self, *a, **k: None,
                }
                if module_name == 'downloader.youtube' and cls == 'YoutubeDownloader':
                    attrs['download_link'] = lambda self, *a, **k: None
                setattr(mod, cls, type(cls, (), attrs))
            return mod

        modules_to_stub = {
            'downloader.youtube': ['YoutubeDownloader'],
            'downloader.soundcloud': ['SoundcloudDownloader'],
            'downloader.telegram': ['TelegramDownloader'],
            'processing.converter': ['Converter'],
            'processing.epsflattener': ['EpsFlattener'],
            'processing.extractor': ['Extractor'],
            'processing.mover': ['Mover'],
            'processing.renamer': ['Renamer'],
            'postprocessing.repair': ['FileRepair'],
            'postprocessing.sanitizer': ['Sanitizer'],
            'postprocessing.tagger': ['Tagger'],
            'postprocessing.analyze': ['Analyze'],
            'postprocessing.artistfixer': ['ArtistFixer'],
        }

        for mod_name in set(m.split('.')[0] for m in modules_to_stub):
            if mod_name not in sys.modules:
                original_modules[mod_name] = None
                sys.modules[mod_name] = types.ModuleType(mod_name)

        for full_name, classes in modules_to_stub.items():
            original_modules[full_name] = sys.modules.get(full_name)
            sys.modules[full_name] = _make_stub_module(full_name, classes)

        from step import Step as RealStep
        original_modules['main'] = sys.modules.get('main')
        main_mod = types.ModuleType('main')
        main_mod.Step = RealStep
        sys.modules['main'] = main_mod

        with patch('api.db_init.ensure_tables_exist') as ensure_mock:
            import api.server as server_module
            importlib.reload(server_module)
            with TestClient(server_module.app):
                pass
            ensure_mock.assert_called_once()

        for name, mod in original_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


if __name__ == '__main__':
    unittest.main()
