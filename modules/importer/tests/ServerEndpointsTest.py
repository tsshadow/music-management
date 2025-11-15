import importlib
import json
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '3306')
os.environ.setdefault('DB_USER', 'user')
os.environ.setdefault('DB_PASS', 'pass')
os.environ.setdefault('DB_DB', 'db')


class ServerEndpointsTest(unittest.TestCase):
    def setUp(self):
        self.original_modules = {}

        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"
        os.environ['CONFIG_PATH'] = str(self.config_path)

        import api.config_store as config_store
        self.config_store_module = importlib.reload(config_store)
        self.config_store_module.ConfigStore._reset_for_tests()

        def _make_stub_module(module_name, class_names):
            mod = types.ModuleType(module_name)
            for cls in class_names:
                attrs = {"run": lambda self: None}
                if module_name == "postprocessing.tagger" and cls == "Tagger":
                    def _parse_song(path, *_args, manual_tags=None, **_kwargs):
                        song_cls = getattr(mod, "LabelSong", None)
                        if song_cls is None:
                            return None
                        song = song_cls()
                        parse = getattr(song, "parse", None)
                        if callable(parse):
                            parse()
                        if manual_tags and hasattr(song, "tag_collection"):
                            for tag, value in manual_tags.items():
                                add = getattr(song.tag_collection, "add", None)
                                if callable(add):
                                    add(tag, value)
                        save = getattr(song, "save_file", None)
                        if callable(save):
                            save()
                        return song
                    attrs["parse_song"] = staticmethod(_parse_song)
                setattr(mod, cls, type(cls, (), attrs))
            sys.modules[module_name] = mod
            if module_name == "postprocessing.tagger":
                setattr(mod, "LabelSong", type("LabelSong", (), {}))

        # stub modules used by steps
        self._stub_modules = {
            "processing.extractor": ["Extractor"],
            "processing.renamer": ["Renamer"],
            "processing.mover": ["Mover"],
            "processing.converter": ["Converter"],
            "postprocessing.sanitizer": ["Sanitizer"],
            "postprocessing.repair": ["FileRepair"],
            "processing.epsflattener": ["EpsFlattener"],
            "downloader.youtube": ["YoutubeDownloader"],
            "downloader.soundcloud": ["SoundcloudDownloader"],
            "downloader.telegram": ["TelegramDownloader"],
            "postprocessing.analyze": ["Analyze"],
            "postprocessing.artistfixer": ["ArtistFixer"],
            "postprocessing.tagger": ["Tagger"],
        }

        for name, classes in self._stub_modules.items():
            self.original_modules[name] = sys.modules.get(name)
            _make_stub_module(name, classes)

        # Make sure no previously imported modules keep stale state
        for name in list(sys.modules):
            if name.startswith('api.') or name in {'api', 'step'}:
                self.original_modules.setdefault(name, sys.modules[name])
                del sys.modules[name]

        # Provide a minimal Step definition used by server
        class RealStep:
            def __init__(self, name, selectors, func):
                self.name = name
                self.selectors = selectors
                self.func = func

            def should_run(self, selected):
                return bool(set(self.selectors) & set(selected)) or 'all' in selected

            def run(self, selected, **kwargs):
                self.func()

        self.original_modules['step'] = sys.modules.get('step')
        step_module = types.ModuleType('step')
        step_module.Step = RealStep
        sys.modules['step'] = step_module

        import api.server as server_module
        self.server = importlib.reload(server_module)
        self.server.ensure_yt_dlp_is_updated = lambda: None
        self.Step = RealStep
        self.server.jobs.clear()

    def tearDown(self):
        for name, mod in self.original_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
        os.environ.pop('CONFIG_PATH', None)
        self.config_store_module.ConfigStore._reset_for_tests()
        self.temp_dir.cleanup()

    def test_steps_and_jobs_listing(self):
        with TestClient(self.server.app) as client:
            resp = client.get('/api/steps')
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn('steps', data)

            job_resp = client.post('/api/run/manual-youtube', json={'url': 'http://example.com'})
            self.assertEqual(job_resp.status_code, 200)
            job_id = job_resp.json()['id']

            time.sleep(0.1)

            jobs_resp = client.get('/api/jobs')
            self.assertEqual(jobs_resp.status_code, 200)
            jobs = jobs_resp.json()['jobs']
            self.assertTrue(any(job['id'] == job_id and job['step'] == 'manual-youtube' for job in jobs))

    def test_config_get_and_update(self):
        store = self.config_store_module.ConfigStore()
        with TestClient(self.server.app) as client:
            resp = client.get('/api/config')
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn('fields', data)
            keys = [field['key'] for field in data['fields']]
            self.assertIn('import_folder_path', keys)

            payload = {
                'import_folder_path': '/var/imports',
                'telegram_max_concurrent': 8,
            }
            update = client.patch('/api/config', json={'updates': payload})
            self.assertEqual(update.status_code, 200)
            result = update.json()['values']
            self.assertEqual(result['import_folder_path'], '/var/imports')
            self.assertEqual(result['telegram_max_concurrent'], 8)

            invalid = client.patch('/api/config', json={'updates': {'telegram_max_concurrent': 'nope'}})
            self.assertEqual(invalid.status_code, 422)

        self.assertEqual(store.get('import_folder_path'), '/var/imports')
        self.assertEqual(store.get('telegram_max_concurrent'), 8)
        self.assertTrue(self.config_path.exists())
        with self.config_path.open() as fh:
            persisted = json.load(fh)
        self.assertEqual(persisted['import_folder_path'], '/var/imports')

    def test_run_manual_youtube(self):
        with TestClient(self.server.app) as client:
            resp = client.post('/api/run/manual-youtube', json={'url': 'http://example.com'})
            self.assertEqual(resp.status_code, 200)
            job = resp.json()
            self.assertIn('id', job)
            self.assertEqual(job['step'], 'manual-youtube')

    def test_run_manual_youtube_missing_url(self):
        with TestClient(self.server.app) as client:
            resp = client.post('/api/run/manual-youtube', json={})
            self.assertEqual(resp.status_code, 400)

    def test_stop_job(self):
        with TestClient(self.server.app) as client:
            resp = client.post('/api/run/manual-youtube', json={'url': 'http://example.com', 'repeat': True})
            self.assertEqual(resp.status_code, 200)
            job_id = resp.json()['id']

            stop_resp = client.post(f'/api/job/{job_id}/stop')
            self.assertEqual(stop_resp.status_code, 200)
            job = stop_resp.json()
            self.assertEqual(job['status'], 'stopped')

    def test_unknown_step(self):
        with TestClient(self.server.app) as client:
            resp = client.post('/api/run/unknown-step', json={})
            self.assertEqual(resp.status_code, 404)

    def test_job_not_found(self):
        with TestClient(self.server.app) as client:
            resp = client.get('/api/job/nonexistent')
            self.assertEqual(resp.status_code, 404)

    def test_stop_job_not_found(self):
        with TestClient(self.server.app) as client:
            resp = client.post('/api/job/nonexistent/stop')
            self.assertEqual(resp.status_code, 404)


if __name__ == '__main__':
    unittest.main()
