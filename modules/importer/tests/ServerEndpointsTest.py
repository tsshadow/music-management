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

        self.music_root = Path(self.temp_dir.name) / "Music"
        self.youtube_dir = self.music_root / "Youtube"
        self.soundcloud_dir = self.music_root / "Soundcloud"
        self.telegram_dir = self.music_root / "Telegram"

        def _make_stub_module(module_name, class_names):
            outer_self = self
            mod = types.ModuleType(module_name)
            if module_name == "downloader.youtube":
                class YoutubeDownloader:
                    def __init__(self, *args, **kwargs):
                        self.output_folder = str(outer_self.youtube_dir)
                        self.manual = []
                        self.accounts = []

                    def run(self):
                        self.manual.append(("run", None))

                    def manual_download(self, url, *_args, **_kwargs):
                        self.manual.append(("url", url))

                    def manual_account_download(self, account, *_args, **_kwargs):
                        self.accounts.append(account)

                setattr(mod, "YoutubeDownloader", YoutubeDownloader)
            elif module_name == "downloader.soundcloud":
                class SoundcloudDownloader:
                    def __init__(self, break_on_existing=True, *args, **kwargs):
                        self.output_folder = str(outer_self.soundcloud_dir)
                        self.default_break_on_existing = break_on_existing
                        self.calls = []

                    def run(self, account="", breakOnExisting=None, redownload=False):
                        self.calls.append({
                            "account": account,
                            "break": breakOnExisting,
                            "redownload": redownload,
                        })

                setattr(mod, "SoundcloudDownloader", SoundcloudDownloader)
            elif module_name == "downloader.telegram":
                class TelegramDownloader:
                    def __init__(self, *args, **kwargs):
                        self.output_folder = str(outer_self.telegram_dir)
                        self.calls = []

                    def run(self, channel, limit=None):
                        self.calls.append({"channel": channel, "limit": limit})

                setattr(mod, "TelegramDownloader", TelegramDownloader)
            elif module_name == "postprocessing.tagger":
                class Tagger:
                    def __init__(self):
                        self.run_calls = []
                        self.parse_calls = []

                    def run(self, **kwargs):
                        self.run_calls.append(kwargs)

                    def parse_folder(self, folder, song_type):
                        self.parse_calls.append((str(folder), getattr(song_type, "name", song_type)))

                setattr(mod, "Tagger", Tagger)
            else:
                for cls in class_names:
                    attrs = {"run": lambda self, *a, **k: None}
                    setattr(mod, cls, type(cls, (), attrs))
            sys.modules[module_name] = mod

        # stub modules used by steps
        self._stub_modules = {
            "processing.extractor": ["Extractor"],
            "processing.renamer": ["Renamer"],
            "processing.mover": ["Mover"],
            "processing.converter": ["Converter"],
            "postprocessing.sanitizer": ["Sanitizer"],
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

        store = self.config_store_module.ConfigStore()
        store.update({
            "music_folder_path": str(self.music_root),
            "youtube_folder": str(self.youtube_dir),
            "youtube_archive": str(self.youtube_dir / "archive.txt"),
            "soundcloud_folder": str(self.soundcloud_dir),
            "soundcloud_archive": str(self.soundcloud_dir / "archive.txt"),
            "telegram_folder": str(self.telegram_dir),
        })

        # Make sure no previously imported modules keep stale state
        for name in list(sys.modules):
            if name.startswith('api.') or name.startswith('modules.importer.api') or name in {'api'}:
                self.original_modules.setdefault(name, sys.modules[name])
                del sys.modules[name]

        import api.server as server_module
        self.server = importlib.reload(server_module)
        self.server.ensure_yt_dlp_is_updated = lambda: None
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

            detail = client.get(f'/api/job/{job_id}')
            self.assertEqual(detail.status_code, 200)
            detail_payload = detail.json()
            self.assertEqual(detail_payload['parameters'].get('url'), 'http://example.com')
            self.assertIn('result', detail_payload)
            self.assertIn('downloads', detail_payload['result'])

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
            self.assertEqual(job['parameters']['url'], 'http://example.com')

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
